from django.core.management.base import BaseCommand
from django.conf import settings
from pathlib import Path
import shutil
from sklepzdoniczkami.models import Product

class Command(BaseCommand):
    help = 'Copy docs/sample-images into MEDIA_ROOT/products and assign them to the first products as product.image (URL path)'

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        docs_dir = base / 'docs' / 'sample-images'
        media_products = Path(settings.MEDIA_ROOT) / 'products'
        media_products.mkdir(parents=True, exist_ok=True)

        images = sorted([p for p in docs_dir.iterdir() if p.suffix.lower() in {'.svg','.png','.jpg','.jpeg'}])
        if not images:
            self.stdout.write(self.style.WARNING('No sample images found in docs/sample-images'))
            return

        # copy images to media/products
        copied = []
        for img in images:
            dest = media_products / img.name
            shutil.copyfile(img, dest)
            copied.append(dest)
            self.stdout.write(f'Copied {img.name} -> {dest}')

        # assign to products
        products = list(Product.objects.all()[:len(copied)])
        if not products:
            self.stdout.write(self.style.WARNING('No products found to assign images to.'))
            return

        for product, img in zip(products, copied):
            # store relative media URL
            product.image = f'{settings.MEDIA_URL}products/{img.name}'
            product.save(update_fields=['image'])
            self.stdout.write(self.style.SUCCESS(f'Assigned {img.name} to product {product.pk} ({product.name})'))

        self.stdout.write(self.style.SUCCESS('Sample images loaded and assigned.'))
