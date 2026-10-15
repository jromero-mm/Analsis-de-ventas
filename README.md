# Análisis de ventas — demostración

Aplicación local de Python y Tkinter para analizar ventas por local, laboratorio y producto, guardar selecciones y exportar reportes a Excel.

Esta copia contiene nombres, metas y configuraciones ficticios. No incluye reportes reales, perfiles de trabajo, ejecutables ni respaldos del proyecto original. Las opciones de agrupación y conversión de unidades se configuran explícitamente, sin excepciones asociadas a proveedores reales.

## Ejecutar en Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config/laboratorios.example.json config/laboratorios.json
Copy-Item config/perfiles.example.json config/perfiles.json
Copy-Item config/concursos.example.json config/concursos.json
.\.venv\Scripts\python.exe -m app.main
```

Copiar una tabla con encabezados `Botica`, `Laboratorio`, `CantE`, `CantF` y `TotalP`; opcionalmente `Descripción Producto` y `Presentación`. Pulsar «Leer portapapeles», elegir laboratorios o cargar el perfil DEMO, analizar y exportar. La exportación guarda un archivo con nombre único y solicita abrirlo en la aplicación asociada a Excel.

Datos ficticios para copiar desde una hoja de cálculo:

| Botica | Laboratorio | Descripción Producto | CantE | CantF | TotalP |
|---|---|---|---:|---:|---:|
| LOCAL 001 | LABORATORIO DEMO | PRODUCTO A | 1 | 2 | 20 |
| LOCAL 002 | LABORATORIO DEMO | PRODUCTO B | 0 | 4 | 15 |

El perfil DEMO incluye también PRODUCTO C, que debe aparecer en cero.

Las preferencias se guardan en la carpeta de usuario `AnalisisVentasDemo`, separada de la aplicación de trabajo. Los JSON de uso local y los reportes están excluidos de Git; únicamente las plantillas `*.example.json` deben publicarse. Mantener esas plantillas siempre ficticias.

## Verificar y compilar

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m app.main --selftest
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

El ejecutable se genera en `dist/AnalisisVentasDemo`. La compilación requiere Python con Tkinter en Windows. Esta copia incluye una selección de pruebas genéricas; las pruebas dependientes de datos y reglas originales no se distribuyen.

