"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy

from sklepzdoniczkami.auth_views import (
    AdminPasswordResetView,
    AdminPasswordResetForm,
)

from sklepzdoniczkami.seo import robots_txt, sitemap_xml

urlpatterns = [
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap_xml, name='sitemap_xml'),
    path(
        'admin/password_reset/',
        AdminPasswordResetView.as_view(
            form_class=AdminPasswordResetForm,
            email_template_name='admin/password_reset_email.txt',
            subject_template_name='admin/password_reset_subject.txt',
            template_name='admin/password_reset_form.html',
            success_url=reverse_lazy('admin_password_reset_done'),
        ),
        name='admin_password_reset',
    ),
    path(
        'admin/password_reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='admin/password_reset_done.html',
        ),
        name='admin_password_reset_done',
    ),
    path(
        'admin/reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='admin/password_reset_confirm.html',
            success_url=reverse_lazy('admin_password_reset_complete'),
        ),
        name='admin_password_reset_confirm',
    ),
    path(
        'admin/reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='admin/password_reset_complete.html',
        ),
        name='admin_password_reset_complete',
    ),
    path('admin/', admin.site.urls),
    path('', include('sklepzdoniczkami.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
