from inventory.services import get_variants_inventory


def build_product_inventory_context(products):
    """
    Build one grouped inventory snapshot for a collection of products.
    Products should have their variants prefetched.
    """
    variants = {}

    for product in products:
        for variant in product.variants.all():
            variants[variant.pk] = variant

    return {
        "variant_inventory": get_variants_inventory(variants.values())
    }