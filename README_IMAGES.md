Sample images and loading

This project includes a small set of sample product images in docs/sample-images/ to help with visual testing.

To load them into your local development media and assign to products:

1. Ensure MEDIA_ROOT exists and Django settings point to it (default: media/).
2. Run the management command:

    python manage.py load_sample_images

This will copy files from docs/sample-images into media/products/ and assign them to the first products in the database by primary key order (one image per product).

Notes:
- These files are intentionally small SVG placeholders for local testing. For production, upload real optimized JPEG/WEBP images and use a proper media storage.
- The Product.image field stores a URL/path (string). In templates, product.image is used directly as the image src.
