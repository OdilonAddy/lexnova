from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q
from datetime import datetime, date, timedelta
from .models import Cliente, Pago, Audiencia, Tarea, Documento
from django.contrib.auth.models import User
from functools import wraps
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from django.utils import timezone
from num2words import num2words
import csv
import os
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import mimetypes

from django.db import models
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Cliente, Pago, Tarea, Audiencia
from datetime import date, datetime, timedelta
from io import BytesIO

import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import F, Value

def requiere_permiso(permiso):
    """Decorador para verificar permisos específicos"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            try:
                from .models import PerfilUsuario
                perfil = PerfilUsuario.objects.get(user=request.user)
                
                if permiso == 'clientes' and not (perfil.puede_gestionar_clientes or perfil.es_administrador):
                    messages.error(request, 'No tienes permisos para gestionar clientes')
                    return redirect('dashboard')
                elif permiso == 'agenda' and not (perfil.puede_gestionar_agenda or perfil.es_administrador):
                    messages.error(request, 'No tienes permisos para gestionar agenda')
                    return redirect('dashboard')
                elif permiso == 'pagos' and not (perfil.puede_gestionar_pagos or perfil.es_administrador):
                    messages.error(request, 'No tienes permisos para gestionar pagos')
                    return redirect('dashboard')
                elif permiso == 'documentos' and not (perfil.puede_gestionar_documentos or perfil.es_administrador):
                    messages.error(request, 'No tienes permisos para gestionar documentos')
                    return redirect('dashboard')
                elif permiso == 'admin' and not perfil.es_administrador:
                    messages.error(request, 'No tienes permisos de administrador')
                    return redirect('dashboard')
                    
            except PerfilUsuario.DoesNotExist:
                # Si no existe perfil, es el primer usuario (admin por defecto)
                pass
                
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def login_view(request):
    """Vista de login personalizada"""
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos')
    
    return render(request, 'lex_nova/login.html')

def logout_view(request):
    """Vista de logout"""
    logout(request)
    return redirect('login')

@login_required
def dashboard(request):
    """Dashboard principal con widgets y configuración"""
    from .models import ConfiguracionEmpresa, PerfilUsuario
    from datetime import datetime
    
    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after_tomorrow = today + timedelta(days=2)
    
    # Procesar actualización de configuración
    if request.method == 'POST':
        config = ConfiguracionEmpresa.get_configuracion()
        config.direccion = request.POST.get('direccion', config.direccion)
        config.telefono = request.POST.get('telefono', config.telefono)
        config.email = request.POST.get('email', config.email)
        config.save()
        messages.success(request, 'Configuración actualizada exitosamente')
        return redirect('dashboard')
    
    # Obtener permisos del usuario actual
    try:
        perms_usuario = PerfilUsuario.objects.get(user=request.user)
    except PerfilUsuario.DoesNotExist:
        perms_usuario = None
    
    # Hora actual
    hora_actual = datetime.now().time()
    
    # Tareas y audiencias
    tareas_hoy = Tarea.objects.filter(fecha=today, estado='PENDIENTE')
    tareas_manana = Tarea.objects.filter(fecha=tomorrow, estado='PENDIENTE')
    tareas_pasado_manana = Tarea.objects.filter(fecha=day_after_tomorrow, estado='PENDIENTE')
    
    # Tareas vencidas - SOLO fechas anteriores a hoy
    # Las de hoy con hora pasada se manejarán en el frontend o se vencen a las 00:00 del día siguiente
    tareas_vencidas = Tarea.objects.filter(fecha__lt=today, estado='PENDIENTE')
    
    audiencias_hoy = Audiencia.objects.filter(fecha=today)
    audiencias_manana = Audiencia.objects.filter(fecha=tomorrow)
    audiencias_pasado_manana = Audiencia.objects.filter(fecha=day_after_tomorrow)
    
    # Configuración de empresa
    config_empresa = ConfiguracionEmpresa.get_configuracion()
    
    # Lista de usuarios (solo para admin)
    usuarios_sistema = []
    if perms_usuario and perms_usuario.es_administrador:
        usuarios_sistema = User.objects.all()
    
    context = {
        'tareas_hoy': tareas_hoy,
        'tareas_manana': tareas_manana,
        'tareas_pasado_manana': tareas_pasado_manana,
        'tareas_vencidas': tareas_vencidas,
        'audiencias_hoy': audiencias_hoy,
        'audiencias_manana': audiencias_manana,
        'audiencias_pasado_manana': audiencias_pasado_manana,
        'fecha_actual': today,
        'config_empresa': config_empresa,
        'perms_usuario': perms_usuario,
        'usuarios_sistema': usuarios_sistema,
    }
    
    return render(request, 'lex_nova/dashboard.html', context)

# ============================================
# GESTIÓN DE CLIENTES
# ============================================

@login_required
@requiere_permiso('clientes')
def gestion_clientes(request):
    """Vista de gestión de clientes y casos"""
    clientes = Cliente.objects.all()
    
    # Filtros de búsqueda
    search = request.GET.get('search')
    if search:
        clientes = clientes.filter(
            Q(nurej__icontains=search) |
            Q(cedula__icontains=search) |
            Q(nombre__icontains=search)
        )
    
    context = {
        'clientes': clientes,
        'search': search,
    }
    
    return render(request, 'lex_nova/gestion_clientes.html', context)
@login_required
@requiere_permiso('clientes')
def agregar_cliente(request):
    """Vista para agregar nuevo cliente"""
    if request.method == 'POST':
        try:
            pago_inicial = request.POST.get('pago_inicial', 0)
            
            cliente = Cliente.objects.create(
                nurej=request.POST['nurej'],
                cedula=request.POST['cedula'],
                nombre=request.POST['nombre'],
                telefono=request.POST['telefono'],
                tipo_proceso=request.POST['tipo_proceso'],
                juzgado=request.POST['juzgado'],
                honorarios_pactados=request.POST['honorarios_pactados'],
                pago_inicial=pago_inicial,
                ultima_actuacion=request.POST.get('ultima_actuacion', ''),
                proxima_actuacion=request.POST.get('proxima_actuacion', ''),
            )
            
            # Agregar fecha de última actuación si existe
            fecha_ultima = request.POST.get('fecha_ultima_actuacion')
            if fecha_ultima:
                cliente.fecha_ultima_actuacion = fecha_ultima
                cliente.save()
                
                # CREAR TAREA AUTOMÁTICA DE REVISIÓN 3 DÍAS HÁBILES DESPUÉS
                fecha_base = datetime.strptime(fecha_ultima, '%Y-%m-%d').date()
                dias_habiles_agregados = 0
                fecha_revision = fecha_base
                
                while dias_habiles_agregados < 3:
                    fecha_revision += timedelta(days=1)
                    # Verificar si es día hábil (lunes=0, domingo=6)
                    if fecha_revision.weekday() < 5:  # Lunes a viernes
                        dias_habiles_agregados += 1
                
                Tarea.objects.create(
                    tipo='REVISION',
                    descripcion='Revisar expediente físico en juzgados',
                    fecha=fecha_revision,
                    cliente=cliente,
                    estado='PENDIENTE'
                )
            
            # Crear pago automático si hay pago inicial
            if pago_inicial and float(pago_inicial) > 0:
                Pago.objects.create(
                    cliente=cliente,
                    monto=pago_inicial,
                    fecha=date.today()
                )
            
            messages.success(request, 'Cliente registrado exitosamente')
            # DEVOLVER EL ID DEL CLIENTE PARA PODER IMPRIMIR LA FICHA
            return JsonResponse({
                'success': True,
                'cliente_id': cliente.id,
                'cliente_nombre': cliente.nombre
            })
        except Exception as e:
            messages.error(request, f'Error al registrar cliente: {str(e)}')
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False})


@login_required
@requiere_permiso('clientes')
def editar_datos(request):
    """Vista para editar datos del cliente"""
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        
        try:
            cliente = get_object_or_404(Cliente, id=cliente_id)
            
            # Actualizar solo los campos que tienen valor
            nurej = request.POST.get('nurej', '').strip()
            if nurej:
                cliente.nurej = nurej
            
            cedula = request.POST.get('cedula', '').strip()
            if cedula:
                cliente.cedula = cedula
            
            nombre = request.POST.get('nombre', '').strip()
            if nombre:
                cliente.nombre = nombre
            
            telefono = request.POST.get('telefono', '').strip()
            if telefono:
                cliente.telefono = telefono
            
            tipo_proceso = request.POST.get('tipo_proceso', '').strip()
            if tipo_proceso:
                cliente.tipo_proceso = tipo_proceso
            
            juzgado = request.POST.get('juzgado', '').strip()
            if juzgado:
                cliente.juzgado = juzgado
            
            honorarios_pactados = request.POST.get('honorarios_pactados', '').strip()
            if honorarios_pactados:
                cliente.honorarios_pactados = honorarios_pactados
            
            pago_inicial = request.POST.get('pago_inicial', '').strip()
            if pago_inicial:
                cliente.pago_inicial = pago_inicial
            
            ultima_actuacion = request.POST.get('ultima_actuacion', '').strip()
            if ultima_actuacion:
                cliente.ultima_actuacion = ultima_actuacion
            
            proxima_actuacion = request.POST.get('proxima_actuacion', '').strip()
            if proxima_actuacion:
                cliente.proxima_actuacion = proxima_actuacion
            
            fecha_ultima = request.POST.get('fecha_ultima_actuacion', '').strip()
            if fecha_ultima:
                cliente.fecha_ultima_actuacion = fecha_ultima
            
            cliente.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Cambios realizados con éxito'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al editar datos: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Método no permitido'})

@login_required
@requiere_permiso('clientes')
def cambiar_estado(request):
    """Vista para cambiar estado del cliente"""
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        nuevo_estado = request.POST.get('estado')
        
        try:
            cliente = get_object_or_404(Cliente, id=cliente_id)
            cliente.estado = nuevo_estado
            cliente.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Cambios realizados con éxito'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al cambiar estado: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Método no permitido'})

@login_required
@requiere_permiso('clientes')
def eliminar_cliente(request):
    """Vista para eliminar cliente"""
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        
        try:
            cliente = get_object_or_404(Cliente, id=cliente_id)
            nombre_cliente = cliente.nombre
            cliente.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Cliente {nombre_cliente} eliminado exitosamente'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al eliminar cliente: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Método no permitido'})

@login_required
@requiere_permiso('clientes')
def registrar_pago(request):
    """Vista para registrar un nuevo pago"""
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        monto = request.POST.get('monto')
        fecha = request.POST.get('fecha')
        
        try:
            cliente = get_object_or_404(Cliente, id=cliente_id)
            
            # Crear el nuevo pago
            pago = Pago.objects.create(
                cliente=cliente,
                monto=monto,
                fecha=fecha
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Pago registrado exitosamente',
                'nuevo_total': float(cliente.total_pagado()),
                'nuevo_saldo': float(cliente.saldo_adeudado())
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al registrar pago: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Método no permitido'})

@login_required
@requiere_permiso('clientes')
def programar_audiencia(request):
    """Vista para programar una nueva audiencia"""
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        detalle = request.POST.get('detalle')
        fecha = request.POST.get('fecha')
        hora = request.POST.get('hora')
        
        try:
            cliente = get_object_or_404(Cliente, id=cliente_id)
            
            # Crear la nueva audiencia
            audiencia = Audiencia.objects.create(
                cliente=cliente,
                detalle=detalle,
                fecha=fecha,
                hora=hora
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Audiencia programada con éxito'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al programar audiencia: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Método no permitido'})

@login_required
@requiere_permiso('clientes')
def insertar_actuacion(request):
    """Vista para insertar nueva actuación"""
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        nueva_ultima_actuacion = request.POST.get('nueva_ultima_actuacion')
        fecha_ultima_actuacion = request.POST.get('fecha_ultima_actuacion')
        proxima_actuacion = request.POST.get('proxima_actuacion')
        
        try:
            cliente = get_object_or_404(Cliente, id=cliente_id)
            
            # Actualizar la actuación del cliente
            cliente.ultima_actuacion = nueva_ultima_actuacion
            cliente.fecha_ultima_actuacion = fecha_ultima_actuacion
            cliente.proxima_actuacion = proxima_actuacion
            cliente.save()
            
            # Crear tarea automática de revisión 3 DÍAS HÁBILES después
            if fecha_ultima_actuacion:
                fecha_base = datetime.strptime(fecha_ultima_actuacion, '%Y-%m-%d').date()
                dias_habiles_agregados = 0
                fecha_revision = fecha_base
                
                while dias_habiles_agregados < 3:
                    fecha_revision += timedelta(days=1)
                    # Verificar si es día hábil (lunes=0 a viernes=4, sábado=5, domingo=6)
                    if fecha_revision.weekday() < 5:  # Lunes a viernes
                        dias_habiles_agregados += 1
                
                Tarea.objects.create(
                    tipo='REVISION',
                    descripcion='Revisar expediente físico en juzgados',
                    fecha=fecha_revision,
                    cliente=cliente,
                    estado='PENDIENTE'
                )
            
            return JsonResponse({
                'success': True,
                'message': 'Última actuación actualizada'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al actualizar actuación: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Método no permitido'})

# ============================================
# AGENDA Y TAREAS
# ============================================

@login_required
@requiere_permiso('agenda')
def agenda_tareas(request):
    """Vista de agenda y tareas con estadísticas"""
    hoy = date.today()
    
    # Obtener TODAS las tareas (completadas y pendientes)
    todas_las_tareas = Tarea.objects.all().order_by('fecha', 'hora')
    tareas_solo_pendientes = Tarea.objects.filter(estado='PENDIENTE').order_by('fecha', 'hora')
    
    # Contar estadísticas (solo pendientes para los widgets)
    tareas_hoy = tareas_solo_pendientes.filter(fecha=hoy).count()
    tareas_pendientes = tareas_solo_pendientes.count()
    tareas_vencidas = tareas_solo_pendientes.filter(fecha__lt=hoy).count()
    audiencias_mes = Audiencia.objects.filter(
        fecha__month=hoy.month,
        fecha__year=hoy.year
    ).count()
    
    context = {
        'tareas': todas_las_tareas,
        'tareas_hoy': tareas_hoy,
        'tareas_pendientes': tareas_pendientes,
        'tareas_vencidas': tareas_vencidas,
        'audiencias_mes': audiencias_mes,
        'hoy': hoy,
    }
    return render(request, 'lex_nova/agenda_tareas.html', context)

@login_required
@requiere_permiso('agenda')
def crear_tarea(request):
    """Crear nueva tarea"""
    if request.method == 'POST':
        tipo = request.POST.get('tipo', 'tarea')
        descripcion = request.POST.get('descripcion')
        fecha = request.POST.get('fecha')
        hora = request.POST.get('hora', None)
        relacion = request.POST.get('relacion')
        cliente_id = request.POST.get('cliente_id')
        
        tarea = Tarea(
            tipo=tipo.upper(),
            descripcion=descripcion,
            fecha=fecha,
            estado='PENDIENTE'
        )
        
        if hora:
            tarea.hora = hora
            
        if relacion == 'cliente' and cliente_id:
            try:
                cliente = Cliente.objects.get(Q(nurej=cliente_id) | Q(cedula=cliente_id))
                tarea.cliente = cliente
            except Cliente.DoesNotExist:
                messages.error(request, 'Cliente no encontrado')
                return redirect('agenda_tareas')
                
        tarea.save()
        messages.success(request, 'Tarea creada exitosamente')
        
    return redirect('agenda_tareas')

@login_required
@requiere_permiso('agenda')
def completar_tarea(request, tarea_id):
    """Marcar tarea como completada"""
    if request.method == 'POST':
        try:
            tarea = get_object_or_404(Tarea, id=tarea_id)
            tarea.estado = 'COMPLETADA'
            tarea.save()
            messages.success(request, 'Tarea completada exitosamente')
        except Exception as e:
            messages.error(request, f'Error al completar tarea: {str(e)}')
    return redirect('agenda_tareas')

@login_required
@requiere_permiso('agenda')
def eliminar_tarea(request, tarea_id):
    """Eliminar tarea"""
    if request.method == 'POST':
        try:
            tarea = get_object_or_404(Tarea, id=tarea_id)
            tarea.delete()
            messages.success(request, 'Tarea eliminada exitosamente')
        except Exception as e:
            messages.error(request, f'Error al eliminar tarea: {str(e)}')
    return redirect('agenda_tareas')

@login_required
@requiere_permiso('agenda')
def editar_tarea(request, tarea_id):
    """Editar tarea existente"""
    if request.method == 'POST':
        try:
            tarea = get_object_or_404(Tarea, id=tarea_id)
            
            # Siempre actualizar fecha y hora
            tarea.fecha = request.POST.get('fecha')
            nueva_hora = request.POST.get('hora')
            tarea.hora = nueva_hora if nueva_hora else None
            
            # Actualizar otros campos si se proporcionaron
            if request.POST.get('descripcion'):
                tarea.descripcion = request.POST.get('descripcion')
            
            if request.POST.get('tipo'):
                tarea.tipo = request.POST.get('tipo', '').upper()
            
            # Si se edita una tarea completada, marcarla como pendiente
            if tarea.estado == 'COMPLETADA':
                tarea.estado = 'PENDIENTE'
            
            # Manejar relación con cliente
            relacion = request.POST.get('relacion')
            if relacion:
                cliente_id = request.POST.get('cliente_id')
                if relacion == 'cliente' and cliente_id:
                    try:
                        cliente = Cliente.objects.get(Q(nurej=cliente_id) | Q(cedula=cliente_id))
                        tarea.cliente = cliente
                    except Cliente.DoesNotExist:
                        messages.warning(request, 'Cliente no encontrado, tarea guardada sin cliente')
                elif relacion == 'independiente':
                    tarea.cliente = None
            
            tarea.save()
            messages.success(request, 'Tarea editada exitosamente')
            
        except Exception as e:
            messages.error(request, f'Error al editar tarea: {str(e)}')
    
    return redirect('agenda_tareas')

# ============================================
# PAGOS Y FINANZAS
# ============================================

@login_required
@requiere_permiso('pagos')
def pagos_finanzas(request):
    """Vista de pagos y finanzas con filtros funcionales"""
    pagos = Pago.objects.all().select_related('cliente').order_by('-fecha')
    
    # Aplicar filtros
    search = request.GET.get('search')
    if search:
        pagos = pagos.filter(
            Q(cliente__nurej__icontains=search) |
            Q(cliente__cedula__icontains=search) |
            Q(cliente__nombre__icontains=search)
        )
    
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    
    if fecha_desde:
        pagos = pagos.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        pagos = pagos.filter(fecha__lte=fecha_hasta)
    
    # Obtener clientes para resumen
    clientes_resumen = Cliente.objects.all()
    
    # Calcular estadísticas básicas
    total_cobrado = sum(float(pago.monto) for pago in pagos)
    pagos_este_mes = pagos.filter(fecha__month=date.today().month).count()
    
    context = {
        'pagos': pagos,
        'clientes_resumen': clientes_resumen,
        'total_cobrado': total_cobrado,
        'total_por_cobrar': 0,
        'pagos_este_mes': pagos_este_mes,
        'pagos_vencidos': 0,
        'search': search,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'hoy': date.today(),
    }
    
    return render(request, 'lex_nova/pagos_finanzas.html', context)

@login_required
@requiere_permiso('pagos')
def crear_pago(request):
    """Crear nuevo pago con validaciones"""
    if request.method == 'POST':
        try:
            cliente_nurej = request.POST.get('cliente_nurej')
            
            # Validar que existe el cliente
            try:
                cliente = Cliente.objects.get(nurej=cliente_nurej)
            except Cliente.DoesNotExist:
                messages.error(request, f'Cliente con NUREJ {cliente_nurej} no encontrado. Verifique el número.')
                return redirect('pagos_finanzas')
            
            pago = Pago.objects.create(
                cliente=cliente,
                monto=request.POST.get('monto'),
                fecha=request.POST.get('fecha')
            )
            
            messages.success(request, f'¡Pago registrado exitosamente! ${pago.monto} de {cliente.nombre}')
            
        except Exception as e:
            messages.error(request, f'Error al registrar pago: {str(e)}')
    
    return redirect('pagos_finanzas')

@login_required
@requiere_permiso('pagos')
def editar_pago(request, pago_id):
    """Editar pago existente"""
    if request.method == 'POST':
        try:
            pago = get_object_or_404(Pago, id=pago_id)
            
            pago.monto = request.POST.get('monto')
            pago.fecha = request.POST.get('fecha')
            pago.save()
            
            messages.success(request, 'Pago editado exitosamente')
            
        except Exception as e:
            messages.error(request, f'Error al editar pago: {str(e)}')
    
    return redirect('pagos_finanzas')

@login_required
@requiere_permiso('pagos')
def eliminar_pago(request, pago_id):
    """Eliminar pago"""
    if request.method == 'POST':
        try:
            pago = get_object_or_404(Pago, id=pago_id)
            monto = pago.monto
            cliente = pago.cliente.nombre
            pago.delete()
            
            messages.success(request, f'Pago de ${monto} de {cliente} eliminado exitosamente')
            
        except Exception as e:
            messages.error(request, f'Error al eliminar pago: {str(e)}')
    
    return redirect('pagos_finanzas')

@login_required
@requiere_permiso('pagos')
def exportar_pagos_pdf(request):
    """Exportar reporte de pagos a PDF elegante con filtros"""
    try:
        from .models import ConfiguracionEmpresa
        config_empresa = ConfiguracionEmpresa.get_configuracion()
        
        # Obtener filtros
        nurej_filtro = request.GET.get('nurej_filtro', '')
        fecha_desde = request.GET.get('fecha_desde', '')
        fecha_hasta = request.GET.get('fecha_hasta', '')
        
        # Filtrar pagos
        pagos = Pago.objects.all().select_related('cliente').order_by('-fecha')
        
        if nurej_filtro:
            pagos = pagos.filter(cliente__nurej__icontains=nurej_filtro)
        if fecha_desde:
            pagos = pagos.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            pagos = pagos.filter(fecha__lte=fecha_hasta)
        
        # Crear respuesta PDF
        response = HttpResponse(content_type='application/pdf')
        
        if nurej_filtro:
            filename = f"reporte_pagos_{nurej_filtro}_{timezone.now().strftime('%Y%m%d')}.pdf"
        else:
            filename = f"reporte_pagos_general_{timezone.now().strftime('%Y%m%d')}.pdf"
            
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Estilos personalizados
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Title'],
            fontSize=18,
            fontName='Helvetica-Bold',
            textColor=colors.Color(0.1, 0.2, 0.5),
            alignment=TA_CENTER,
            spaceAfter=20
        )
        
        header_style = ParagraphStyle(
            'HeaderStyle',
            parent=styles['Normal'],
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=colors.Color(0.2, 0.3, 0.6),
            alignment=TA_CENTER,
            spaceAfter=15
        )
        
        info_style = ParagraphStyle(
            'InfoStyle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.Color(0.3, 0.3, 0.3),
            alignment=TA_CENTER,
            spaceAfter=8
        )
        
        # Encabezado del reporte
        story.append(Paragraph("LEXNOVA & ASOCIADOS - ABOGADOS", title_style))
        story.append(Paragraph(f"{config_empresa.direccion or 'Zona 12 de Octubre, Avenida Franco Valle'}", info_style))
        story.append(Paragraph(f"Teléfono: {config_empresa.telefono or '+591 78793765'} | Email: {config_empresa.email or 'contacto@lexnova.bo'}", info_style))
        story.append(Spacer(1, 15))
        
        # Título del reporte
        if nurej_filtro:
            titulo_reporte = f"REPORTE DE PAGOS - CLIENTE NUREJ: {nurej_filtro}"
        else:
            titulo_reporte = "REPORTE GENERAL DE PAGOS"
            
        story.append(Paragraph(titulo_reporte, header_style))
        
        # Información del filtro
        filtro_info = []
        if fecha_desde and fecha_hasta:
            filtro_info.append(f"Período: {fecha_desde} al {fecha_hasta}")
        elif fecha_desde:
            filtro_info.append(f"Desde: {fecha_desde}")
        elif fecha_hasta:
            filtro_info.append(f"Hasta: {fecha_hasta}")
        
        if filtro_info:
            story.append(Paragraph(" | ".join(filtro_info), info_style))
            
        story.append(Spacer(1, 15))
        
        # Preparar datos para la tabla
        data = [['NOMBRE', 'NUREJ', 'MONTO DE PAGO', 'FECHA DE PAGO']]
        
        total_general = 0
        
        for pago in pagos:
            data.append([
                pago.cliente.nombre,
                str(pago.cliente.nurej),
                f'Bs {pago.monto:,.2f}',
                pago.fecha.strftime('%d/%m/%Y')
            ])
            total_general += float(pago.monto)
        
        # Agregar filas vacías para completar el diseño
        while len(data) < 8:  # Mínimo 7 filas de datos + encabezado
            data.append(['', '', '', ''])
        
        # Fila de total
        data.append(['', '', 'TOTAL GENERAL:', f'Bs {total_general:,.2f}'])
        
        # Crear tabla con estilo elegante
        table = Table(data, colWidths=[2.5*inch, 1.2*inch, 1.3*inch, 1.3*inch])
        table.setStyle(TableStyle([
            # Encabezado principal
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.1, 0.4, 0.1)),  # Verde oscuro
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Datos
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -2), 9),
            ('ALIGN', (0, 1), (0, -2), 'LEFT'),    # Nombres alineados a la izquierda
            ('ALIGN', (1, 1), (-1, -2), 'CENTER'), # NUREJ, monto y fecha centrados
            
            # Fila de total
            ('BACKGROUND', (0, -1), (-1, -1), colors.Color(0.1, 0.4, 0.1)),  # Verde oscuro
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
            ('ALIGN', (0, -1), (-1, -1), 'CENTER'),
            
            # Bordes
            ('GRID', (0, 0), (-1, -1), 1.5, colors.Color(0.1, 0.4, 0.1)),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.Color(0.1, 0.4, 0.1)),
            ('LINEABOVE', (0, -1), (-1, -1), 2, colors.Color(0.1, 0.4, 0.1)),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            
            # Alternar colores en filas de datos
            ('BACKGROUND', (0, 1), (-1, -2), colors.Color(0.95, 0.98, 0.95)),  # Verde muy claro
            ('BACKGROUND', (0, 2), (-1, -2), colors.white),  # Blanco alternado (esto se aplicará a filas pares)
        ]))
        
        # Aplicar colores alternados manualmente
        for i in range(1, len(data) - 1):  # Excluir encabezado y total
            if i % 2 == 0:  # Filas pares
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, i), (-1, i), colors.Color(0.95, 0.98, 0.95))
                ]))
        
        story.append(table)
        story.append(Spacer(1, 20))
        
        # Pie de página
        pie_data = [
            [f'Reporte generado por LexNova & Asociados - Abogados'],
            [f'{timezone.now().strftime("%d de %B de %Y a las %H:%M")}']
        ]
        
        pie_table = Table(pie_data, colWidths=[6*inch])
        pie_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.grey),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ]))
        story.append(pie_table)
        
        # Construir PDF
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar reporte: {str(e)}')
        return redirect('pagos_finanzas')

@login_required 
def generar_recibo_pago(request, pago_id):
    """Generar recibo de pago final corregido"""
    try:
        pago = get_object_or_404(Pago, id=pago_id)
        from .models import ConfiguracionEmpresa
        config_empresa = ConfiguracionEmpresa.get_configuracion()
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="recibo_{pago.id}_{pago.cliente.nombre.replace(" ", "_")}.pdf"'
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.2*inch, bottomMargin=0.2*inch)
        
        def crear_recibo(es_original=True):
            story = []
            styles = getSampleStyleSheet()
            
            # Estilos
            marca_style = ParagraphStyle(
                'MarcaStyle',
                parent=styles['Normal'],
                fontSize=12,
                fontName='Helvetica-Bold',
                textColor=colors.Color(0.1, 0.2, 0.5),
                spaceAfter=1,
                spaceBefore=0
            )
            
            info_style = ParagraphStyle(
                'InfoStyle',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.Color(0.3, 0.3, 0.3),
                spaceAfter=1,
                spaceBefore=0
            )
            
            header_style = ParagraphStyle(
                'HeaderStyle',
                parent=styles['Normal'],
                fontSize=12,
                fontName='Helvetica-Bold',
                textColor=colors.Color(0.2, 0.3, 0.6),
                alignment=TA_CENTER,
                spaceAfter=3,
                spaceBefore=2
            )
            
            tipo_style = ParagraphStyle(
                'TipoStyle',
                parent=styles['Normal'],
                fontSize=7,
                textColor=colors.grey,
                alignment=TA_RIGHT,
                spaceAfter=0,
                spaceBefore=0
            )
            
            # Encabezado con marca alineada a la izquierda
            tipo_recibo = "ORIGINAL" if es_original else "COPIA"
            
            encabezado_data = [
                [
                    Paragraph("LEXNOVA & ASOCIADOS - ABOGADOS", marca_style),
                    Paragraph(tipo_recibo, tipo_style)
                ]
            ]
            
            encabezado_table = Table(encabezado_data, colWidths=[4.5*inch, 1.5*inch])
            encabezado_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(encabezado_table)
            
            # Información de contacto alineada a la izquierda
            story.append(Paragraph(f"{config_empresa.direccion or 'Zona 12 de Octubre, Avenida Franco Valle'}", info_style))
            story.append(Paragraph(f"Teléfono: {config_empresa.telefono or '+591 78793765'} | Email: {config_empresa.email or 'contacto@lexnova.bo'}", info_style))
            story.append(Spacer(1, 4))
            
            # Título del recibo
            story.append(Paragraph(f"RECIBO DE PAGO N° {pago.id:04d}", header_style))
            story.append(Spacer(1, 4))
            
            # Información del cliente
            info_data = [
                ['Recibido de:', pago.cliente.nombre, 'Fecha:', pago.fecha.strftime('%d de %B de %Y')],
                ['Documento:', str(pago.cliente.nurej), 'Tipo Proceso:', pago.cliente.tipo_proceso],
            ]
            
            info_table = Table(info_data, colWidths=[0.9*inch, 2.1*inch, 0.8*inch, 1.7*inch])
            info_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.Color(0.2, 0.3, 0.6)),
                ('BACKGROUND', (0, 0), (0, -1), colors.Color(0.93, 0.95, 0.98)),
                ('BACKGROUND', (2, 0), (2, -1), colors.Color(0.93, 0.95, 0.98)),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(info_table)
            story.append(Spacer(1, 4))
            
            # Detalle del servicio
            detalle_data = [
                ['DESCRIPCIÓN DEL SERVICIO', 'CANT.', 'PRECIO UNIT.', 'IMPORTE'],
                ['Honorarios profesionales por servicios jurídicos', '1', f'Bs {pago.monto:,.2f}', f'Bs {pago.monto:,.2f}'],
                ['', '', '', ''],
                ['', '', 'TOTAL A PAGAR:', f'Bs {pago.monto:,.2f}'],
            ]
            
            detalle_table = Table(detalle_data, colWidths=[2.8*inch, 0.5*inch, 1.2*inch, 1.2*inch])
            detalle_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.3, 0.6)),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('ALIGN', (1, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                ('FONTNAME', (2, 3), (-1, 3), 'Helvetica-Bold'),
                ('FONTSIZE', (2, 3), (-1, 3), 9),
                ('BACKGROUND', (2, 3), (-1, 3), colors.Color(0.9, 0.95, 1.0)),
                ('GRID', (0, 0), (-1, -1), 1, colors.Color(0.2, 0.3, 0.6)),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(detalle_table)
            story.append(Spacer(1, 4))
            
            # Monto en letras
            try:
                monto_entero = int(float(pago.monto))
                centavos = int((float(pago.monto) - monto_entero) * 100)
                monto_letras = num2words(monto_entero, lang='es').upper()
                texto_literal = f'SON: Bs {pago.monto:,.2f} ({monto_letras} BOLIVIANOS {centavos:02d}/100)'
            except:
                texto_literal = f'SON: Bs {pago.monto} BOLIVIANOS'
            
            literal_data = [[texto_literal]]
            literal_table = Table(literal_data, colWidths=[5.7*inch])
            literal_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, 0), colors.Color(0.95, 0.97, 1.0)),
                ('GRID', (0, 0), (0, 0), 1, colors.Color(0.2, 0.3, 0.6)),
                ('FONTSIZE', (0, 0), (0, 0), 8),
                ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                ('TOPPADDING', (0, 0), (0, 0), 3),
                ('BOTTOMPADDING', (0, 0), (0, 0), 3),
            ]))
            story.append(literal_table)
            story.append(Spacer(1, 15))
            
            # Firmas corregidas con más espacio
            firma_data = [
                ['', ''],
                ['', ''],
                ['_' * 30, '_' * 30],
                ['ENTREGUE CONFORME', 'RECIBÍ CONFORME'],
                [pago.cliente.nombre, 'LexNova & Asociados - Abogados'],
                [f'C.I.: {pago.cliente.nurej}', 'Representante Legal'],
            ]
            
            firma_table = Table(firma_data, colWidths=[2.85*inch, 2.85*inch])
            firma_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 3), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            story.append(firma_table)
            story.append(Spacer(1, 8))
            
            # Pie de página
            pie_texto = f'Generado por LexNova &amp; Asociados - Abogados | {timezone.now().strftime("%d/%m/%Y a las %H:%M")}'
            story.append(Paragraph(pie_texto, ParagraphStyle('Footer', parent=info_style, alignment=TA_CENTER, fontSize=6, textColor=colors.grey)))
            
            return story
        
        # Crear ambos recibos
        elementos = []
        
        # ORIGINAL
        elementos.extend(crear_recibo(es_original=True))
        
        # Separador
        elementos.append(Spacer(1, 6))
        elementos.append(Paragraph('— ' * 40, ParagraphStyle('Sep', parent=getSampleStyleSheet()['Normal'], alignment=TA_CENTER, fontSize=6, textColor=colors.grey)))
        elementos.append(Spacer(1, 4))
        
        # COPIA
        elementos.extend(crear_recibo(es_original=False))
        
        doc.build(elementos)
        
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar recibo: {str(e)}')
        return redirect('pagos_finanzas')

# ============================================
# DOCUMENTOS Y REPORTES
# ============================================

@login_required
@requiere_permiso('documentos')
def documentos_reportes(request):
    """Vista de documentos y reportes"""
    documentos = Documento.objects.all()
    context = {
        'documentos': documentos,
    }
    return render(request, 'lex_nova/documentos_reportes.html', context)

# ============================================
# GESTIÓN DE USUARIOS
# ============================================

@login_required
@requiere_permiso('admin')
def crear_usuario(request):
    """Crear nuevo usuario con permisos específicos"""
    from .models import PerfilUsuario
    
    if request.method == 'POST':
        try:
            # Crear usuario
            usuario = User.objects.create_user(
                username=request.POST.get('username'),
                email=request.POST.get('email'),
                password=request.POST.get('password'),
                first_name=request.POST.get('full_name')
            )
            
            # Obtener permisos seleccionados
            permisos = request.POST.getlist('permisos')
            
            # Crear perfil con permisos específicos
            perfil = PerfilUsuario.objects.create(
                user=usuario,
                puede_gestionar_clientes='clientes' in permisos,
                puede_gestionar_agenda='agenda' in permisos,
                puede_gestionar_pagos='pagos' in permisos,
                puede_gestionar_documentos='documentos' in permisos,
                es_administrador='admin' in permisos,
                puede_crear_usuarios='admin' in permisos,
                puede_modificar_config='admin' in permisos
            )
            
            messages.success(request, f'Usuario {usuario.username} creado exitosamente con permisos específicos')
            
        except Exception as e:
            messages.error(request, f'Error al crear usuario: {str(e)}')
    
    return redirect('dashboard')

@login_required
@requiere_permiso('agenda')
def reprogramar_tarea(request, tarea_id):
    """Reprogramar tarea completada"""
    if request.method == 'POST':
        try:
            tarea = get_object_or_404(Tarea, id=tarea_id)
            tarea.estado = 'PENDIENTE'
            tarea.save()
            messages.success(request, 'Tarea reprogramada exitosamente')
        except Exception as e:
            messages.error(request, f'Error al reprogramar tarea: {str(e)}')
    return redirect('agenda_tareas')

# ============================================
# DOCUMENTOS Y REPORTES - FUNCIONES COMPLETAS
# ============================================

@login_required
@requiere_permiso('documentos')
def documentos_reportes(request):
    """Vista de documentos y reportes con filtros funcionales"""
    documentos = Documento.objects.all().order_by('-fecha_subida')
    
    # Aplicar filtros
    search = request.GET.get('search')
    if search:
        documentos = documentos.filter(nombre__icontains=search)
    
    cliente_search = request.GET.get('cliente_search')
    if cliente_search:
        documentos = documentos.filter(
            Q(cliente__nurej__icontains=cliente_search) |
            Q(cliente__cedula__icontains=cliente_search) |
            Q(cliente__nombre__icontains=cliente_search)
        )
    
    tipo_filtro = request.GET.get('tipo')
    if tipo_filtro and tipo_filtro != 'Todos':
        documentos = documentos.filter(tipo=tipo_filtro.lower())
    
    fecha_filtro = request.GET.get('fecha')
    if fecha_filtro:
        documentos = documentos.filter(fecha_subida=fecha_filtro)
    
    context = {
        'documentos': documentos,
        'search': search,
        'cliente_search': cliente_search,
        'tipo_filtro': tipo_filtro,
        'fecha_filtro': fecha_filtro,
    }
    return render(request, 'lex_nova/documentos_reportes.html', context)

@login_required
@requiere_permiso('documentos')
def subir_documento(request):
    """Subir nuevo documento con validaciones"""
    if request.method == 'POST':
        try:
            archivo = request.FILES.get('archivo')
            tipo = request.POST.get('tipo')
            cliente_id = request.POST.get('cliente_id')
            descripcion = request.POST.get('descripcion', '')
            
            if not archivo:
                messages.error(request, 'Debe seleccionar un archivo')
                return JsonResponse({'success': False})
            
            # Validar tipo de archivo
            extensiones_permitidas = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.png', '.jpeg']
            nombre_archivo = archivo.name.lower()
            if not any(nombre_archivo.endswith(ext) for ext in extensiones_permitidas):
                messages.error(request, 'Tipo de archivo no permitido')
                return JsonResponse({'success': False})
            
            # Buscar cliente si se proporcionó
            cliente = None
            if cliente_id:
                try:
                    cliente = Cliente.objects.get(
                        Q(nurej=cliente_id) | Q(cedula=cliente_id)
                    )
                except Cliente.DoesNotExist:
                    messages.warning(request, 'Cliente no encontrado. Documento guardado sin asociar')
            
            # Crear documento
            documento = Documento.objects.create(
                nombre=archivo.name,
                archivo=archivo,
                tipo=tipo,
                cliente=cliente,
                descripcion=descripcion,
                tamaño=archivo.size
            )
            
            messages.success(request, f'Documento "{archivo.name}" subido exitosamente')
            return JsonResponse({'success': True})
            
        except Exception as e:
            messages.error(request, f'Error al subir documento: {str(e)}')
            return JsonResponse({'success': False})
    
    return JsonResponse({'success': False})
@login_required
@requiere_permiso('documentos')
def ver_documento(request, documento_id):
    """Ver documento en el navegador"""
    try:
        documento = get_object_or_404(Documento, id=documento_id)
        
        # Obtener el tipo MIME del archivo
        content_type, _ = mimetypes.guess_type(documento.archivo.name)
        if not content_type:
            content_type = 'application/octet-stream'
        
        response = HttpResponse(documento.archivo.read(), content_type=content_type)
        response['Content-Disposition'] = f'inline; filename="{documento.nombre}"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al ver documento: {str(e)}')
        return redirect('documentos_reportes')

@login_required
@requiere_permiso('documentos')
def descargar_documento(request, documento_id):
    """Descargar documento"""
    try:
        documento = get_object_or_404(Documento, id=documento_id)
        
        response = HttpResponse(documento.archivo.read(), content_type='application/force-download')
        response['Content-Disposition'] = f'attachment; filename="{documento.nombre}"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al descargar documento: {str(e)}')
        return redirect('documentos_reportes')

@login_required
@requiere_permiso('documentos')
def eliminar_documento(request, documento_id):
    """Eliminar documento"""
    if request.method == 'POST':
        try:
            documento = get_object_or_404(Documento, id=documento_id)
            nombre = documento.nombre
            
            # Eliminar archivo físico
            if documento.archivo:
                documento.archivo.delete()
            
            # Eliminar registro de base de datos
            documento.delete()
            
            messages.success(request, f'Documento "{nombre}" eliminado exitosamente')
            return JsonResponse({'success': True})
            
        except Exception as e:
            messages.error(request, f'Error al eliminar documento: {str(e)}')
            return JsonResponse({'success': False})
    
    return JsonResponse({'success': False})
@login_required
@requiere_permiso('documentos')
def generar_reporte_casos(request):
    """Generar reporte de casos judiciales"""
    try:
        from .models import ConfiguracionEmpresa
        config_empresa = ConfiguracionEmpresa.get_configuracion()
        
        response = HttpResponse(content_type='application/pdf')
        filename = f"reporte_casos_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Estilos
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Title'],
            fontSize=18,
            fontName='Helvetica-Bold',
            textColor=colors.Color(0.1, 0.2, 0.5),
            alignment=TA_CENTER,
            spaceAfter=20
        )
        
        # Encabezado
        story.append(Paragraph("LEXNOVA & ASOCIADOS - ABOGADOS", title_style))
        story.append(Paragraph("REPORTE DE CASOS JUDICIALES", title_style))
        story.append(Spacer(1, 20))
        
        # Obtener todos los clientes
        clientes = Cliente.objects.all().order_by('estado', 'nombre')
        
        # Preparar datos para la tabla
        data = [['CLIENTE', 'NUREJ', 'TIPO PROCESO', 'JUZGADO', 'ESTADO', 'ÚLTIMA ACTUACIÓN']]
        
        for cliente in clientes:
            data.append([
                cliente.nombre,
                str(cliente.nurej),
                cliente.tipo_proceso,
                cliente.juzgado or 'N/A',
                cliente.estado,
                cliente.fecha_ultima_actuacion.strftime('%d/%m/%Y') if cliente.fecha_ultima_actuacion else 'N/A'
            ])
        
        # Crear tabla
        table = Table(data, colWidths=[1.5*inch, 0.8*inch, 1.2*inch, 1.2*inch, 0.8*inch, 1.0*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.1, 0.4, 0.1)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(table)
        story.append(Spacer(1, 20))
        
        # Estadísticas
        total_casos = clientes.count()
        casos_activos = clientes.filter(estado='ACTIVO').count()
        casos_concluidos = clientes.filter(estado='CONCLUIDO').count()
        
        stats_data = [
            ['ESTADÍSTICAS GENERALES'],
            [f'Total de casos: {total_casos}'],
            [f'Casos activos: {casos_activos}'],
            [f'Casos concluidos: {casos_concluidos}'],
        ]
        
        stats_table = Table(stats_data, colWidths=[3*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.Color(0.1, 0.4, 0.1)),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(stats_table)
        
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar reporte: {str(e)}')
        return redirect('documentos_reportes')

@login_required
@requiere_permiso('documentos')
def generar_reporte_audiencias(request):
    """Generar reporte de audiencias programadas"""
    try:
        from .models import ConfiguracionEmpresa
        config_empresa = ConfiguracionEmpresa.get_configuracion()
        
        response = HttpResponse(content_type='application/pdf')
        filename = f"calendario_audiencias_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Estilos
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Title'],
            fontSize=18,
            fontName='Helvetica-Bold',
            textColor=colors.Color(0.1, 0.2, 0.5),
            alignment=TA_CENTER,
            spaceAfter=20
        )
        
        # Encabezado
        story.append(Paragraph("LEXNOVA & ASOCIADOS - ABOGADOS", title_style))
        story.append(Paragraph("CALENDARIO DE AUDIENCIAS", title_style))
        story.append(Spacer(1, 20))
        
        # Obtener audiencias próximas (próximos 30 días)
        fecha_limite = date.today() + timedelta(days=30)
        audiencias = Audiencia.objects.filter(
            fecha__gte=date.today(),
            fecha__lte=fecha_limite
        ).order_by('fecha', 'hora')
        
        # Preparar datos para la tabla
        data = [['FECHA', 'HORA', 'CLIENTE', 'DETALLE', 'JUZGADO']]
        
        for audiencia in audiencias:
            data.append([
                audiencia.fecha.strftime('%d/%m/%Y'),
                audiencia.hora.strftime('%H:%M') if audiencia.hora else 'N/A',
                audiencia.cliente.nombre,
                audiencia.detalle,
                audiencia.cliente.juzgado or 'N/A'
            ])
        
        if not audiencias:
            data.append(['No hay audiencias programadas', '', '', '', ''])
        
        # Crear tabla
        table = Table(data, colWidths=[1*inch, 0.8*inch, 1.5*inch, 2*inch, 1.2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.8, 0.4, 0.1)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('ALIGN', (0, 1), (1, -1), 'CENTER'),
            ('ALIGN', (2, 1), (-1, -1), 'LEFT'),
        ]))
        
        story.append(table)
        
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar reporte: {str(e)}')
        return redirect('documentos_reportes')

@login_required
@requiere_permiso('documentos')
def generar_reporte_expedientes(request):
    """Generar reporte de expedientes pendientes de revisión"""
    try:
        from .models import ConfiguracionEmpresa
        config_empresa = ConfiguracionEmpresa.get_configuracion()
        
        response = HttpResponse(content_type='application/pdf')
        filename = f"revision_expedientes_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Estilos
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Title'],
            fontSize=18,
            fontName='Helvetica-Bold',
            textColor=colors.Color(0.1, 0.2, 0.5),
            alignment=TA_CENTER,
            spaceAfter=20
        )
        
        # Encabezado
        story.append(Paragraph("LEXNOVA & ASOCIADOS - ABOGADOS", title_style))
        story.append(Paragraph("REVISIÓN DE EXPEDIENTES", title_style))
        story.append(Spacer(1, 20))
        
        # Obtener tareas de revisión pendientes
        tareas_revision = Tarea.objects.filter(
            tipo='REVISION',
            estado='PENDIENTE'
        ).order_by('fecha')
        
        # Preparar datos para la tabla
        data = [['FECHA REVISIÓN', 'CLIENTE', 'NUREJ', 'JUZGADO', 'DÍAS PENDIENTES']]
        
        hoy = date.today()
        for tarea in tareas_revision:
            dias_pendientes = (hoy - tarea.fecha).days if tarea.fecha <= hoy else 0
            estado_dias = f"{dias_pendientes} días" if dias_pendientes > 0 else "Pendiente"
            
            data.append([
                tarea.fecha.strftime('%d/%m/%Y'),
                tarea.cliente.nombre if tarea.cliente else 'N/A',
                str(tarea.cliente.nurej) if tarea.cliente else 'N/A',
                tarea.cliente.juzgado if tarea.cliente and tarea.cliente.juzgado else 'N/A',
                estado_dias
            ])
        
        if not tareas_revision:
            data.append(['No hay expedientes pendientes de revisión', '', '', '', ''])
        
        # Crear tabla
        table = Table(data, colWidths=[1.2*inch, 1.8*inch, 1*inch, 1.5*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.1, 0.6, 0.8)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (4, 1), (4, -1), 'CENTER'),
        ]))
        
        story.append(table)
        
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar reporte: {str(e)}')
        return redirect('documentos_reportes')

@login_required
@requiere_permiso('documentos')
def generar_reporte_mensual(request):
    """Generar informe mensual completo"""
    try:
        from .models import ConfiguracionEmpresa
        config_empresa = ConfiguracionEmpresa.get_configuracion()
        
        response = HttpResponse(content_type='application/pdf')
        filename = f"informe_mensual_{timezone.now().strftime('%Y%m')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Estilos
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Title'],
            fontSize=18,
            fontName='Helvetica-Bold',
            textColor=colors.Color(0.1, 0.2, 0.5),
            alignment=TA_CENTER,
            spaceAfter=20
        )
        
        subtitle_style = ParagraphStyle(
            'SubtitleStyle',
            parent=styles['Heading2'],
            fontSize=14,
            fontName='Helvetica-Bold',
            textColor=colors.Color(0.2, 0.3, 0.6),
            spaceAfter=10
        )
        
        # Fecha del reporte
        hoy = date.today()
        primer_dia_mes = hoy.replace(day=1)
        
        # Encabezado
        story.append(Paragraph("LEXNOVA & ASOCIADOS - ABOGADOS", title_style))
        story.append(Paragraph(f"INFORME MENSUAL - {hoy.strftime('%B %Y').upper()}", title_style))
        story.append(Spacer(1, 20))
        
        # RESUMEN DE CASOS
        story.append(Paragraph("RESUMEN DE CASOS", subtitle_style))
        
        total_casos = Cliente.objects.count()
        casos_activos = Cliente.objects.filter(estado='ACTIVO').count()
        casos_nuevos_mes = Cliente.objects.filter(fecha_registro__gte=primer_dia_mes).count()
        
        casos_data = [
            ['INDICADOR', 'CANTIDAD'],
            ['Total de casos', str(total_casos)],
            ['Casos activos', str(casos_activos)],
            ['Casos nuevos este mes', str(casos_nuevos_mes)],
        ]
        
        casos_table = Table(casos_data, colWidths=[3*inch, 1*inch])
        casos_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.1, 0.4, 0.1)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(casos_table)
        story.append(Spacer(1, 15))
        
        # RESUMEN FINANCIERO
        story.append(Paragraph("RESUMEN FINANCIERO", subtitle_style))
        
        pagos_mes = Pago.objects.filter(
            fecha__gte=primer_dia_mes,
            fecha__lte=hoy
        )
        total_cobrado_mes = sum(float(pago.monto) for pago in pagos_mes)
        cantidad_pagos = pagos_mes.count()
        
        finanzas_data = [
            ['INDICADOR', 'MONTO'],
            ['Total cobrado este mes', f'Bs {total_cobrado_mes:,.2f}'],
            ['Cantidad de pagos', str(cantidad_pagos)],
            ['Promedio por pago', f'Bs {(total_cobrado_mes/cantidad_pagos):,.2f}' if cantidad_pagos > 0 else 'Bs 0.00'],
        ]
        
        finanzas_table = Table(finanzas_data, colWidths=[3*inch, 1*inch])
        finanzas_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.1, 0.6, 0.1)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(finanzas_table)
        story.append(Spacer(1, 15))
        
        # AUDIENCIAS DEL MES
        story.append(Paragraph("AUDIENCIAS PROGRAMADAS", subtitle_style))
        
        audiencias_mes = Audiencia.objects.filter(
            fecha__month=hoy.month,
            fecha__year=hoy.year
        ).count()
        
        audiencias_data = [
            ['Total de audiencias este mes', str(audiencias_mes)],
        ]
        
        audiencias_table = Table(audiencias_data, colWidths=[3*inch, 1*inch])
        audiencias_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.8, 0.4, 0.1)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(audiencias_table)
        
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar reporte: {str(e)}')
        return redirect('documentos_reportes')
@login_required
@requiere_permiso('documentos')
def buscar_documentos(request):
    """Buscar documentos con AJAX"""
    if request.method == 'GET':
        query = request.GET.get('q', '')
        
        documentos = Documento.objects.filter(
            Q(nombre__icontains=query) |
            Q(descripcion__icontains=query) |
            Q(cliente__nombre__icontains=query) |
            Q(cliente__nurej__icontains=query)
        ).order_by('-fecha_subida')[:20]
        
        resultados = []
        for doc in documentos:
            resultados.append({
                'id': doc.id,
                'nombre': doc.nombre,
                'tipo': doc.tipo,
                'cliente': doc.cliente.nombre if doc.cliente else 'Sin cliente',
                'fecha': doc.fecha_subida.strftime('%d/%m/%Y'),
                'tamaño': f'{doc.tamaño / 1024:.1f} KB' if doc.tamaño else 'N/A'
            })
        
        return JsonResponse({'documentos': resultados})
    
    return JsonResponse({'documentos': []})

@login_required
@requiere_permiso('clientes')
def exportar_ficha_tecnica(request, cliente_id):
    """Generar ficha técnica del cliente en PDF"""
    try:
        cliente = get_object_or_404(Cliente, id=cliente_id)
        from .models import ConfiguracionEmpresa
        config_empresa = ConfiguracionEmpresa.get_configuracion()
        
        response = HttpResponse(content_type='application/pdf')
        filename = f"ficha_tecnica_{cliente.nombre.replace(' ', '_')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, 
                               topMargin=0.5*inch, 
                               bottomMargin=0.5*inch,
                               leftMargin=0.5*inch,
                               rightMargin=0.5*inch)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Estilo para título
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Title'],
            fontSize=16,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            spaceAfter=10
        )
        
        # Estilo para encabezados de sección
        section_style = ParagraphStyle(
            'SectionStyle',
            parent=styles['Normal'],
            fontSize=11,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            spaceAfter=5,
            spaceBefore=10
        )
        
        # Título principal
        story.append(Paragraph("FICHA TÉCNICA", title_style))
        story.append(Spacer(1, 10))
        
        # AGREGAR LOGO E INFORMACIÓN DE EMPRESA
        from reportlab.platypus import Image as RLImage
        import os
        from django.conf import settings
        
        # Ruta del logo
        logo_path = os.path.join(settings.BASE_DIR, 'gestion/static/images/lexnova_logo.png')
        
        # Crear tabla con logo y datos de empresa
        logo_img = None
        if os.path.exists(logo_path):
            logo_img = RLImage(logo_path, width=3.5*inch, height=2.8*inch)
        
        if logo_img:
            empresa_data = [
                [logo_img],
                [Paragraph(f"{config_empresa.direccion or 'DIRECCIÓN Y TELÉFONO'}", ParagraphStyle('Dir', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER))],
            ]
        else:
            empresa_data = [
                [Paragraph("LEXNOVA", ParagraphStyle('Empresa', parent=styles['Normal'], fontSize=18, fontName='Helvetica-Bold', alignment=TA_CENTER))],
                [Paragraph("ABOGADOS & ASOCIADOS", ParagraphStyle('Sub', parent=styles['Normal'], fontSize=18, alignment=TA_CENTER))],
                [Paragraph(f"{config_empresa.direccion or 'DIRECCIÓN Y TELÉFONO'}", ParagraphStyle('Dir', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER))],
            ]
        
        empresa_table = Table(empresa_data, colWidths=[6.5*inch])
        empresa_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(empresa_table)
        story.append(Spacer(1, 15))
        
        # DATOS DEL CLIENTE
        story.append(Paragraph("DATOS DEL CLIENTE", section_style))
        
        datos_cliente = [
            ['NOMBRE:', cliente.nombre],
            ['NUREJ:', str(cliente.nurej)],
            ['TIPO DE PROCESO:', cliente.tipo_proceso],
            ['JUZGADO:', cliente.juzgado or ''],
            ['TELÉFONO:', cliente.telefono],
        ]
        
        cliente_table = Table(datos_cliente, colWidths=[1.5*inch, 5*inch])
        cliente_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(cliente_table)
        story.append(Spacer(1, 15))
        
        # DETALLE DE HONORARIOS
        story.append(Paragraph("DETALLE DE HONORARIOS", section_style))
        
        # Obtener todos los pagos del cliente
        pagos = Pago.objects.filter(cliente=cliente).order_by('fecha')
        
        honorarios_data = [
            ['PAGOS REALIZADOS', 'MONTO DE PAGO', 'FECHA DE PAGO']
        ]
        
        # Agregar pagos realizados
        for i, pago in enumerate(pagos, 1):
            honorarios_data.append([
                f'PAGO {i}',
                f'Bs {pago.monto:,.2f}',
                pago.fecha.strftime('%d/%m/%Y')
            ])
        
        # Agregar filas vacías si hay menos de 11 pagos
        while len(honorarios_data) < 9:  # 1 encabezado + 11 filas
            honorarios_data.append(['', '', ''])
        
        honorarios_table = Table(honorarios_data, colWidths=[2.5*inch, 2*inch, 2*inch])
        honorarios_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ]))
        story.append(honorarios_table)
        
        # Construir PDF
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar ficha técnica: {str(e)}')
        return redirect('gestion_clientes')
    


@login_required
@requiere_permiso('agenda')
def agregar_tarea(request):
    """Agregar nueva tarea desde el calendario"""
    if request.method == 'POST':
        try:
            from .models import Tarea
            
            cliente_id = request.POST.get('cliente_id')
            cliente = None
            if cliente_id:
                cliente = get_object_or_404(Cliente, id=cliente_id)
            
            tarea = Tarea.objects.create(
                tipo=request.POST.get('tipo_tarea', 'OTRO'),
                descripcion=request.POST.get('descripcion'),
                fecha=request.POST.get('fecha'),
                cliente=cliente,
                estado='PENDIENTE'
            )
            
            return JsonResponse({'success': True, 'message': 'Tarea creada exitosamente'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})


@login_required
@requiere_permiso('agenda')
def agregar_audiencia(request):
    """Agregar nueva audiencia desde el calendario"""
    if request.method == 'POST':
        try:
            from .models import Audiencia
            
            cliente_id = request.POST.get('cliente_id')
            cliente = None
            if cliente_id:
                cliente = get_object_or_404(Cliente, id=cliente_id)
            
            audiencia = Audiencia.objects.create(
                fecha=request.POST.get('fecha'),
                hora=request.POST.get('hora', '00:00'),
                detalle=request.POST.get('descripcion'),
                cliente=cliente
            )
            
            return JsonResponse({'success': True, 'message': 'Audiencia creada exitosamente'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
@requiere_permiso('admin')
def eliminar_usuario(request):
    """Eliminar usuario del sistema"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            usuario_id = data.get('usuario_id')
            
            # No permitir eliminar el propio usuario
            if str(request.user.id) == str(usuario_id):
                return JsonResponse({'success': False, 'error': 'No puedes eliminarte a ti mismo'})
            
            usuario = User.objects.get(id=usuario_id)
            usuario.delete()
            
            return JsonResponse({'success': True})
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Usuario no encontrado'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
@requiere_permiso('agenda')
def exportar_seguimiento(request):
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    import os
    from django.conf import settings
    
    try:
        periodo = request.GET.get('periodo', 'hoy')
        tipos = request.GET.get('tipos', '').split(',')
        
        hoy = date.today()
        
        if periodo == 'hoy':
            fecha_filtro = hoy
            titulo_periodo = "HOY"
        elif periodo == 'manana':
            fecha_filtro = hoy + timedelta(days=1)
            titulo_periodo = "MAÑANA"
        elif periodo == 'pasado_manana':
            fecha_filtro = hoy + timedelta(days=2)
            titulo_periodo = "PASADO MAÑANA"
        else:
            fecha_filtro = None
            titulo_periodo = "VENCIDAS"
        
        eventos = []
        
        for tipo in tipos:
            tipo = tipo.strip()
            
            if tipo == 'AUDIENCIA':
                if fecha_filtro:
                    audiencias = Audiencia.objects.filter(fecha=fecha_filtro)
                else:
                    audiencias = Audiencia.objects.filter(fecha__lt=hoy)
                
                for audiencia in audiencias:
                    cliente = audiencia.cliente
                    saldo = cliente.saldo_adeudado() if cliente else 0
                    
                    # Última actuación del cliente
                    ultima_act = ''
                    fecha_ultima_act = ''
                    if cliente and cliente.ultima_actuacion:
                        ultima_act = cliente.ultima_actuacion[:50]
                        if cliente.fecha_ultima_actuacion:
                            fecha_ultima_act = cliente.fecha_ultima_actuacion.strftime('%b. %d, %Y')
                    
                    eventos.append({
                        'nurej': str(cliente.nurej) if cliente else 'N/A',
                        'nombre': cliente.nombre if cliente else 'Sin cliente',
                        'telefono': cliente.telefono if cliente else 'N/A',
                        'tipo_proceso': cliente.tipo_proceso if cliente else 'N/A',
                        'juzgado': cliente.juzgado if cliente else 'N/A',
                        'saldo': saldo,
                        'ultima_actuacion': ultima_act,
                        'fecha_ultima_actuacion': fecha_ultima_act,
                        'tipo_actuacion': 'AUDIENCIA',
                        'descripcion': audiencia.detalle
                    })
                    
            elif tipo in ['TAREA', 'EVENTO', 'REVISION']:
                if fecha_filtro:
                    tareas = Tarea.objects.filter(fecha=fecha_filtro, tipo=tipo, estado='PENDIENTE')
                else:
                    tareas = Tarea.objects.filter(fecha__lt=hoy, tipo=tipo, estado='PENDIENTE')
                
                for tarea in tareas:
                    cliente = tarea.cliente
                    saldo = cliente.saldo_adeudado() if cliente else 0
                    
                    # Última actuación del cliente
                    ultima_act = ''
                    fecha_ultima_act = ''
                    if cliente and cliente.ultima_actuacion:
                        ultima_act = cliente.ultima_actuacion[:50]
                        if cliente.fecha_ultima_actuacion:
                            fecha_ultima_act = cliente.fecha_ultima_actuacion.strftime('%b. %d, %Y')
                    
                    eventos.append({
                        'nurej': str(cliente.nurej) if cliente else 'N/A',
                        'nombre': cliente.nombre if cliente else 'Sin cliente',
                        'telefono': cliente.telefono if cliente else 'N/A',
                        'tipo_proceso': cliente.tipo_proceso if cliente else 'N/A',
                        'juzgado': cliente.juzgado if cliente else 'N/A',
                        'saldo': saldo,
                        'ultima_actuacion': ultima_act,
                        'fecha_ultima_actuacion': fecha_ultima_act,
                        'tipo_actuacion': tarea.get_tipo_display().upper(),
                        'descripcion': tarea.descripcion
                    })
        
        if not eventos:
            messages.warning(request, 'No hay eventos para exportar con los filtros seleccionados')
            return redirect('dashboard')
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="seguimiento_{periodo}.pdf"'
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), 
                               topMargin=0.3*inch, bottomMargin=0.3*inch,
                               leftMargin=0.3*inch, rightMargin=0.3*inch)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Cargar el logo
        logo_cell = None
        try:
            # Intentar diferentes rutas
            posibles_rutas = [
                os.path.join(settings.BASE_DIR, 'static', 'images', 'lexnova_logo.png'),
                os.path.join(settings.BASE_DIR, 'gestion', 'static', 'images', 'lexnova_logo.png'),
                os.path.join(settings.BASE_DIR, 'staticfiles', 'images', 'lexnova_logo.png'),
            ]
            
            for ruta in posibles_rutas:
                if os.path.exists(ruta):
                    logo_cell = Image(ruta, width=0.9*inch, height=0.9*inch)
                    print(f"Logo cargado desde: {ruta}")
                    break
            
            if logo_cell is None:
                print("Logo no encontrado en ninguna ruta")
        except Exception as e:
            print(f"Error cargando logo: {e}")
        
        # Si no se encontró logo, usar texto
        if logo_cell is None:
            logo_cell = Paragraph('<b>LOGO</b>', ParagraphStyle('Logo', parent=styles['Normal'], fontSize=12, alignment=TA_CENTER))
        
        # Tabla de encabezado
        header_data = [
            [logo_cell, Paragraph('<b>FIRMA JURICA "LEXNOVA - ABOGADOS & ASOCIADOS"</b>', 
                                  ParagraphStyle('Header1', parent=styles['Normal'], fontSize=16, alignment=TA_CENTER))],
            ['', Paragraph('<b>SEGUIMIENTO FISICO DE CASOS EN JUZGADOS</b>', 
                          ParagraphStyle('Header2', parent=styles['Normal'], fontSize=14, alignment=TA_CENTER))]
        ]
        
        header_table = Table(header_data, colWidths=[1*inch, 9.5*inch])
        header_table.setStyle(TableStyle([
            ('SPAN', (0, 0), (0, 1)),
            ('ALIGN', (1, 0), (1, 1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        story.append(header_table)
        story.append(Spacer(1, 10))
        
        # Estilo para texto
        text_style = ParagraphStyle('TextStyle', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER, leading=9)
        header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, leading=10)
        
        # Tabla de datos
        table_data = [[
            Paragraph('<b>NUREJ</b>', header_style),
            Paragraph('<b>Nombre</b>', header_style),
            Paragraph('<b>Teléfono</b>', header_style),
            Paragraph('<b>Tipo<br/>Proceso</b>', header_style),
            Paragraph('<b>Juzgado</b>', header_style),
            Paragraph('<b>Saldo<br/>pendiente<br/>en<br/>honorarios</b>', header_style),
            Paragraph('<b>Última<br/>Actuación</b>', header_style),
            Paragraph('<b>DESCRIPCION<br/>DE<br/>(AUDIENCIA,<br/>TAREA,<br/>REVISION<br/>,ETC)</b>', header_style),
            Paragraph('<b>DETALLE DEL<br/>SEGUIMIENTO</b>', header_style)
        ]]
        
        for evento in eventos:
            # Formatear última actuación con fecha
            ultima_act_texto = ''
            if evento['ultima_actuacion']:
                ultima_act_texto = evento['ultima_actuacion']
                if evento['fecha_ultima_actuacion']:
                    ultima_act_texto += f"<br/>{evento['fecha_ultima_actuacion']}"
            
            # Descripción del evento (tipo + descripción)
            desc_evento = f"{evento['tipo_actuacion']}<br/>{evento['descripcion'][:50]}"
            
            table_data.append([
                Paragraph(str(evento['nurej']), text_style),
                Paragraph(str(evento['nombre'])[:30], text_style),
                Paragraph(str(evento['telefono']), text_style),
                Paragraph(str(evento['tipo_proceso'])[:20], text_style),
                Paragraph(str(evento['juzgado'])[:25], text_style),
                Paragraph(f"${evento['saldo']:.2f}", text_style),
                Paragraph(ultima_act_texto if ultima_act_texto else 'N/A', text_style),
                Paragraph(desc_evento, text_style),
                ''
            ])
        
        # Rellenar filas vacías
        while len(table_data) < 11:
            table_data.append(['', '', '', '', '', '', '', '', ''])
        
        tabla = Table(table_data, colWidths=[0.8*inch, 1*inch, 0.9*inch, 0.8*inch, 0.9*inch, 1*inch, 0.9*inch, 1*inch, 2.3*inch])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        story.append(tabla)
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        
        return response
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        messages.error(request, f'Error al exportar: {str(e)}')
        return redirect('dashboard')
    
@login_required
@requiere_permiso('agenda')
def completar_tarea(request):
    """Marcar tarea como completada"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            tarea_id = data.get('evento_id')
            
            tarea = Tarea.objects.get(id=tarea_id)
            tarea.estado = 'COMPLETADA'
            tarea.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False})


@login_required
@requiere_permiso('agenda')
def editar_tarea(request):
    """Editar tarea"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            tarea_id = data.get('evento_id')
            
            tarea = Tarea.objects.get(id=tarea_id)
            tarea.fecha = data.get('fecha')
            tarea.descripcion = data.get('descripcion')
            tarea.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False})


@login_required
@requiere_permiso('agenda')
def reprogramar_tarea(request):
    """Reprogramar tarea"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            tarea_id = data.get('evento_id')
            
            tarea = Tarea.objects.get(id=tarea_id)
            tarea.fecha = data.get('nueva_fecha')
            tarea.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False})


# Funciones similares para audiencias
@login_required
@requiere_permiso('agenda')
def completar_audiencia(request):
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            audiencia_id = data.get('evento_id')
            
            audiencia = Audiencia.objects.get(id=audiencia_id)
            audiencia.delete()  # O marcar como completada si tienes ese campo
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False})


@login_required
@requiere_permiso('agenda')
def editar_audiencia(request):
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            audiencia_id = data.get('evento_id')
            
            audiencia = Audiencia.objects.get(id=audiencia_id)
            audiencia.fecha = data.get('fecha')
            audiencia.hora = data.get('hora')
            audiencia.detalle = data.get('descripcion')
            audiencia.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False})


@login_required
@requiere_permiso('agenda')
def reprogramar_audiencia(request):
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            audiencia_id = data.get('evento_id')
            
            audiencia = Audiencia.objects.get(id=audiencia_id)
            audiencia.fecha = data.get('nueva_fecha')
            audiencia.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False})

@login_required
@requiere_permiso('agenda')
def detalle_evento(request):
    """Obtener detalles completos de un evento"""
    try:
        evento_id = request.GET.get('id')
        tipo = request.GET.get('tipo')
        
        if tipo == 'tarea':
            evento = Tarea.objects.select_related('cliente').get(id=evento_id)
            data = {
                'success': True,
                'evento': {
                    'nombre': evento.cliente.nombre,
                    'telefono': evento.cliente.telefono,
                    'nurej': evento.cliente.nurej,
                    'tipo_proceso': evento.cliente.tipo_proceso,
                    'juzgado': evento.cliente.juzgado or 'No especificado',
                    'fecha': evento.fecha.strftime('%d/%m/%Y'),
                    'tipo_tarea': evento.get_tipo_display(),
                    'descripcion': evento.descripcion
                }
            }
        else:  # audiencia
            evento = Audiencia.objects.select_related('cliente').get(id=evento_id)
            data = {
                'success': True,
                'evento': {
                    'nombre': evento.cliente.nombre,
                    'telefono': evento.cliente.telefono,
                    'nurej': evento.cliente.nurej,
                    'tipo_proceso': evento.cliente.tipo_proceso,
                    'juzgado': evento.cliente.juzgado or 'No especificado',
                    'fecha': evento.fecha.strftime('%d/%m/%Y'),
                    'hora': evento.hora,
                    'descripcion': evento.detalle
                }
            }
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_http_methods(["POST"])
def completar_tarea(request, tarea_id):
    try:
        tarea = Tarea.objects.get(id=tarea_id)
        tarea.estado = 'COMPLETADA'
        tarea.save()
        return redirect('agenda_tareas')
    except Tarea.DoesNotExist:
        return redirect('agenda_tareas')
    except Exception as e:
        return redirect('agenda_tareas')

@login_required
@require_http_methods(["POST"])
def completar_tarea_json(request):
    try:
        data = json.loads(request.body)
        evento_id = data.get('evento_id')
        
        tarea = Tarea.objects.get(id=evento_id)
        tarea.estado = 'COMPLETADA'
        tarea.save()
        
        return JsonResponse({'success': True})
    except Tarea.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Tarea no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
@login_required
@require_http_methods(["GET"])
def obtener_eventos(request):
    try:
        from django.db.models import F, Value
        
        eventos_lista = []
        
        # Traer TAREAS
        tareas = Tarea.objects.filter(estado='PENDIENTE')
        for tarea in tareas:
            eventos_lista.append({
                'id': tarea.id,
                'tipo': 'tarea',
                'fecha': str(tarea.fecha),
                'descripcion': tarea.descripcion,
                'hora': str(tarea.hora) if tarea.hora else None,
                'cliente': tarea.cliente.nombre if tarea.cliente else 'Sin cliente',
                'nurej': tarea.cliente.nurej if tarea.cliente else '',
                'cliente_id': tarea.cliente.id if tarea.cliente else None,
                'tipoTarea': tarea.tipo
            })
        
        # Traer AUDIENCIAS
        audiencias = Audiencia.objects.all()
        for audiencia in audiencias:
            eventos_lista.append({
                'id': audiencia.id,
                'tipo': 'audiencia',
                'fecha': str(audiencia.fecha),
                'descripcion': audiencia.detalle,
                'hora': str(audiencia.hora) if audiencia.hora else None,
                'cliente': audiencia.cliente.nombre if audiencia.cliente else 'Sin cliente',
                'nurej': audiencia.cliente.nurej if audiencia.cliente else '',
                'cliente_id': audiencia.cliente.id if audiencia.cliente else None,
                'juzgado': audiencia.juzgado if hasattr(audiencia, 'juzgado') else ''
            })
        
        return JsonResponse({'success': True, 'eventos': eventos_lista})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
@login_required
@require_http_methods(["POST"])
def editar_tarea(request):
    try:
        data = json.loads(request.body)
        evento_id = data.get('evento_id')
        
        tarea = Tarea.objects.get(id=evento_id)
        tarea.fecha = data.get('fecha')
        tarea.descripcion = data.get('descripcion')
        tarea.save()
        
        return JsonResponse({'success': True})
    except Tarea.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Tarea no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
@login_required
@require_http_methods(["POST"])
def completar_tarea_json(request):
    try:
        data = json.loads(request.body)
        evento_id = data.get('evento_id')
        
        tarea = Tarea.objects.get(id=evento_id)
        tarea.estado = 'COMPLETADA'
        tarea.save()
        
        return JsonResponse({'success': True})
    except Tarea.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Tarea no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
@login_required
@require_http_methods(["POST"])
def editar_tarea_json(request):
    try:
        data = json.loads(request.body)
        evento_id = data.get('evento_id')
        
        tarea = Tarea.objects.get(id=evento_id)
        tarea.fecha = data.get('fecha')
        tarea.descripcion = data.get('descripcion')
        tarea.hora = data.get('hora') or None
        tarea.save()
        
        return JsonResponse({'success': True})
    except Tarea.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Tarea no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
@login_required
@require_http_methods(["POST"])
def editar_audiencia_json(request):
    try:
        data = json.loads(request.body)
        evento_id = data.get('evento_id')
        
        audiencia = Audiencia.objects.get(id=evento_id)
        audiencia.fecha = data.get('fecha')
        audiencia.detalle = data.get('descripcion')
        audiencia.hora = data.get('hora') or None
        audiencia.save()
        
        return JsonResponse({'success': True})
    except Audiencia.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Audiencia no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
@login_required
@require_http_methods(["POST"])
def reprogramar_tarea_json(request):
    try:
        data = json.loads(request.body)
        evento_id = data.get('evento_id')
        nueva_fecha = data.get('nueva_fecha')
        
        tarea = Tarea.objects.get(id=evento_id)
        tarea.fecha = nueva_fecha
        tarea.save()
        
        return JsonResponse({'success': True})
    except Tarea.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Tarea no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def reprogramar_audiencia_json(request):
    try:
        data = json.loads(request.body)
        evento_id = data.get('evento_id')
        nueva_fecha = data.get('nueva_fecha')
        nueva_hora = data.get('nueva_hora')
        
        audiencia = Audiencia.objects.get(id=evento_id)
        audiencia.fecha = nueva_fecha
        if nueva_hora:
            audiencia.hora = nueva_hora
        audiencia.save()
        
        return JsonResponse({'success': True})
    except Audiencia.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Audiencia no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)