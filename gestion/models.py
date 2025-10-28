from django.db import models
from django.db.models import Sum  # AGREGAR ESTA LÍNEA
from django.contrib.auth.models import User
from django.utils import timezone

class Cliente(models.Model):
    ESTADO_CHOICES = [
        ('ACTIVO', 'Activo'),
        ('CONCLUIDO', 'Concluido'),
        ('ABANDONADO', 'Abandonado'),
    ]
    
    nurej = models.CharField(max_length=50, unique=True, verbose_name="NUREJ")
    cedula = models.CharField(max_length=20, unique=True, verbose_name="Cédula de Identidad")
    nombre = models.CharField(max_length=200, verbose_name="Nombre del Cliente")
    telefono = models.CharField(max_length=15, verbose_name="Teléfono")
    tipo_proceso = models.CharField(max_length=100, verbose_name="Tipo de Proceso")
    juzgado = models.CharField(max_length=200, verbose_name="Juzgado")
    honorarios_pactados = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Honorarios Pactados")
    pago_inicial = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Pago Inicial")
    ultima_actuacion = models.TextField(verbose_name="Última Actuación", blank=True)
    fecha_ultima_actuacion = models.DateField(verbose_name="Fecha de Última Actuación", null=True, blank=True)
    proxima_actuacion = models.TextField(verbose_name="Próxima Actuación", blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='ACTIVO', verbose_name="Estado")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    def total_pagado(self):
        """Calcular total pagado SOLO desde la tabla de Pagos"""
        try:
            from django.db.models import Sum
            total_pagos = self.pagos.aggregate(Sum('monto'))['monto__sum'] or 0
            return float(total_pagos)
        except:
            return 0

    def saldo_adeudado(self):
        """Calcular saldo pendiente"""
        try:
            total_pagado = self.total_pagado()
            return float(self.honorarios_pactados) - float(total_pagado)
        except:
            return 0
    
    def __str__(self):
        return f"{self.nombre} - {self.nurej}"
    
    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['-fecha_creacion']

class Pago(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='pagos')
    monto = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Monto")
    fecha = models.DateField(verbose_name="Fecha de Pago")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.cliente.nombre} - ${self.monto} - {self.fecha}"
    
    class Meta:
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        ordering = ['-fecha']

class Audiencia(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='audiencias')
    detalle = models.TextField(verbose_name="Detalle de la Audiencia")
    fecha = models.DateField(verbose_name="Fecha")
    hora = models.TimeField(verbose_name="Hora")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.cliente.nombre} - {self.detalle} - {self.fecha}"
    
    class Meta:
        verbose_name = "Audiencia"
        verbose_name_plural = "Audiencias"
        ordering = ['fecha', 'hora']

class Tarea(models.Model):
    TIPO_CHOICES = [
        ('TAREA', 'Tarea'),
        ('EVENTO', 'Evento Importante'),
        ('AUDIENCIA', 'Audiencia'),
        ('REVISION', 'Revisión de Expediente'),
    ]
    
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('COMPLETADA', 'Completada'),
    ]
    
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name="Tipo de Actividad")
    descripcion = models.TextField(verbose_name="Descripción")
    fecha = models.DateField(verbose_name="Fecha")
    hora = models.TimeField(verbose_name="Hora", null=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='tareas', null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE', verbose_name="Estado")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        cliente_info = f" - {self.cliente.nombre}" if self.cliente else " - Independiente"
        return f"{self.get_tipo_display()} - {self.descripcion[:50]}{cliente_info}"
    
    class Meta:
        verbose_name = "Tarea"
        verbose_name_plural = "Tareas"
        ordering = ['fecha', 'hora']

class Documento(models.Model):
    TIPO_CHOICES = [
        ('JPG', 'Imagen JPG'),
        ('DOCX', 'Documento Word'),
        ('XLSX', 'Hoja de Cálculo'),
        ('PDF', 'Documento PDF'),
    ]
    
    nombre = models.CharField(max_length=200, verbose_name="Nombre del Documento")
    archivo = models.FileField(upload_to='documentos/', verbose_name="Archivo")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, verbose_name="Tipo")
    descripcion = models.TextField(verbose_name="Descripción", blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='documentos', null=True, blank=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        cliente_info = f" - {self.cliente.nombre}" if self.cliente else " - Independiente"
        return f"{self.nombre}{cliente_info}"
    
    class Meta:
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"
        ordering = ['-fecha_subida']

class ConfiguracionEmpresa(models.Model):
    nombre = models.CharField(max_length=200, default="LEXNOVA & ASOCIADOS")
    direccion = models.CharField(max_length=300, default="Av. [Nombre de la avenida] N° [XXX], Piso [X], La Paz – Bolivia")
    telefono = models.CharField(max_length=100, default="(+591) [Número]")
    email = models.EmailField(default="contacto@lexnova.bo")
    
    class Meta:
        verbose_name = "Configuración de Empresa"
        verbose_name_plural = "Configuración de Empresa"
    
    def __str__(self):
        return self.nombre
    
    @classmethod
    def get_configuracion(cls):
        config, created = cls.objects.get_or_create(id=1)
        return config
class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    puede_gestionar_clientes = models.BooleanField(default=False)
    puede_gestionar_agenda = models.BooleanField(default=False)
    puede_gestionar_pagos = models.BooleanField(default=False)
    puede_gestionar_documentos = models.BooleanField(default=False)
    puede_crear_usuarios = models.BooleanField(default=False)
    puede_modificar_config = models.BooleanField(default=False)
    es_administrador = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Permisos de {self.user.username}"
    
    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuario"
