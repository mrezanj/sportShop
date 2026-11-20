
from rest_framework.throttling import SimpleRateThrottle


class OTPRequestThrottle(SimpleRateThrottle):
    scope = "otp_request"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class OTPVerifyThrottle(SimpleRateThrottle):
    scope = "otp_verify"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }
