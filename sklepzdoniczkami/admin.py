from django.contrib import admin
from .models import Category, Order, OrderItem, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "last_name", "status", "payment_method", "shipping_method", "total", "created_at")
    list_filter = ("status", "payment_method", "shipping_method", "is_paid")
    search_fields = ("first_name", "last_name", "email", "address")
    inlines = [OrderItemInline]
    readonly_fields = ("created_at", "updated_at")
