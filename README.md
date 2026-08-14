# Sistema de Gestión Inteligente para Taller Automotriz con IA 🚗💡

Una API backend moderna y un sistema web impulsado por Inteligencia Artificial para automatizar el registro contable y la administración de talleres mecánicos. Convierte reportes operativos diarios narrados en lenguaje natural a registros estructurados en una base de datos.

## 🚀 Características Principales

* **Procesamiento de Lenguaje Natural:** El personal operativo no necesita llenar formularios complejos. Simplemente escriben lo que hicieron (ej. *"Cambio de frenos placa ABC-123, pagó Carlos 40$"*).
* **Clasificación Automática con IA:** Integración con Google Gemini para analizar el texto, detectar la intención y clasificar automáticamente el registro como "Reparación" (ingreso) o "Gasto", extrayendo datos clave.
* **Almacenamiento Local:** Base de datos estructurada, segura y rápida utilizando SQLite.
* **Exportación Contable a Excel:** Generación de reportes diarios descargables en formato `.xlsx`, con pestañas independientes para ingresos y egresos para un cuadre de caja perfecto.
* **Interfaz de Usuario (UI) Moderna:** Diseño en *Dark Mode* con efectos *Glassmorphism* y detalles en Neón. Completamente *responsive* para ser utilizado cómodamente desde teléfonos móviles en el área de trabajo.

## 🛠️ Tecnologías Utilizadas

* **Backend:** Python, FastAPI, Uvicorn
* **Base de Datos:** SQLite
* **Inteligencia Artificial:** Google GenAI SDK (Modelo `gemini-2.0-flash`)
* **Frontend:** HTML5, CSS3, Vanilla JavaScript (Fetch API)
* **Gestión de Datos:** Pandas, Openpyxl (para la exportación de archivos Excel)

## ⚙️ Instalación y Configuración Local

Si deseas ejecutar este proyecto de forma local, sigue estos pasos:

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/TU_USUARIO/TU_REPOSITORIO.git](https://github.com/TU_USUARIO/TU_REPOSITORIO.git)
   cd TU_REPOSITORIO