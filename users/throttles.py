from rest_framework.exceptions import APIException
from rest_framework import status
from rest_framework.throttling import SimpleRateThrottle
from redis.exceptions import RedisError


class ThrottleBackendUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "OTP throttling service is temporarily unavailable."
    default_code = "throttle_backend_unavailable"


class AtomicRedisRateThrottle(SimpleRateThrottle):
    """
    Fixed-window IP rate limiting using an atomic Redis Lua script.
    """

    script = """
    local count = redis.call('INCR', KEYS[1])

    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end

    return count
    """

    def allow_request(self, request, view):
        self.key = self.get_cache_key(request, view)
        self.history = []
        if self.key is None:
            return True

        cache = self.cache

        try:
            redis_key = cache.make_key(self.key)
            client = cache._cache.get_client(redis_key, write=True)
            count = client.eval(
                self.script,
                1,
                cache.make_key(self.key),
                self.duration,
            )
        except RedisError as exc:
            raise ThrottleBackendUnavailable() from exc
        except Exception as exc:
            raise ThrottleBackendUnavailable() from exc

        return count <= self.num_requests

    def wait(self):
        if self.key is None:
            return None

        try:
            redis_key = self.cache.make_key(self.key)
            client = self.cache._cache.get_client(
                redis_key,
                write=True,
            )
            ttl = client.ttl(redis_key)

            if ttl >= 0:
                return ttl

            if ttl == -1:
                raise ThrottleBackendUnavailable()
        except ThrottleBackendUnavailable:
            raise
        except RedisError as exc:
            raise ThrottleBackendUnavailable() from exc
        except Exception as exc:
            raise ThrottleBackendUnavailable() from exc

        return None


class OTPRequestThrottle(AtomicRedisRateThrottle):
    scope = "otp_request"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class OTPVerifyThrottle(AtomicRedisRateThrottle):
    scope = "otp_verify"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }
