from django.contrib import admin
from .models import Cliente, Pago, Audiencia, Tarea, Documento

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['nurej', 'nombre', 'cedula', 'telefono', 'estado', 'saldo_adeudado']
    list_filter = ['estado', 'tipo_proceso']
    search_fields = ['nurej', 'nombre', 'cedula']

@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ['cliente', 'monto', 'fecha']
    list_filter = ['fecha']

@admin.register(Audiencia)
class AudienciaAdmin(admin.ModelAdmin):
    list_display = ['cliente', 'detalle', 'fecha', 'hora']
    list_filter = ['fecha']

@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ['tipo', 'descripcion', 'cliente', 'fecha', 'estado']
    list_filter = ['tipo', 'estado', 'fecha']

@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'cliente', 'tipo', 'fecha_subida']
    list_filter = ['tipo', 'fecha_subida']