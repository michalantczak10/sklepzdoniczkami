# Sample pot photos

For a local catalog with five example products, run:

```powershell
python manage.py migrate
python manage.py load_sample_products
```

The command is restricted to `APP_ENV=development`, is safe to run repeatedly,
and copies the example photos into `MEDIA_ROOT/products/`. In debug mode,
Django serves these files from `/media/`.

These sample photos are not product-specific sales images. Replace them with
accurate photos of the actual pots before enabling the sample products in a
live catalog.

Photo credits:

- `pot-terracotta-1.jpg` — Vanessa Dyste, [Unsplash](https://unsplash.com/photos/brown-clay-pot-on-gray-concrete-epUnuoLl8es)
- `pot-terracotta-2.jpg` — Annie Spratt, [Unsplash](https://unsplash.com/photos/brown-clay-flower-pots-OlUNA6dteb0)
- `pot-terracotta-3.jpg` — Jona, [Unsplash](https://unsplash.com/photos/green-potted-plant-on-brown-wooden-table-vd0yQBsV0Sw)

The images are used under the Unsplash License. Their photographer attribution
is included here as a courtesy.
