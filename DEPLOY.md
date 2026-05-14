# GUÍA DE DEPLOY — Quick Seguro en Render.com
## Para Andi — sin necesidad de saber programar

---

## PASO 1: Subir el código a GitHub (una sola vez)

1. Entrar a **github.com** y crear una cuenta gratuita (si no tenés)
2. Click en el botón verde **"New"** para crear un repositorio
3. Nombre: `quick-seguro` → click **"Create repository"**
4. En la página que aparece, click en **"uploading an existing file"**
5. Arrastrar todos los archivos de la carpeta `quickseguro/` a esa pantalla:
   - `app.py`
   - `parser.py`
   - `generator.py`
   - `requirements.txt`
   - `Dockerfile`
   - carpeta `templates/` (con los 3 archivos html)
6. Click **"Commit changes"** → ¡listo!

---

## PASO 2: Crear la app en Render (una sola vez)

1. Entrar a **render.com** y crear una cuenta gratuita
2. Click en **"New +"** → **"Web Service"**
3. Conectar con GitHub → seleccionar el repositorio `quick-seguro`
4. Configurar:
   - **Name:** `quick-seguro`
   - **Runtime:** `Docker` (Render lo detecta automáticamente por el Dockerfile)
   - **Plan:** `Free`
5. En la sección **"Environment Variables"**, agregar estas variables:

   | Key | Value |
   |-----|-------|
   | `SECRET_KEY` | (inventar una frase larga, ej: `quickseguro-2024-secreto`) |
   | `USERS` | `francisco:TU_PASS,empleado1:SU_PASS,empleado2:SU_PASS` |

6. Click **"Create Web Service"**
7. Esperar 3-5 minutos mientras Render construye la app
8. Render te da una URL como `https://quick-seguro.onrender.com`
9. ¡Listo! Compartir esa URL con los empleados

---

## PASO 3: Uso diario

Los empleados entran a la URL, se loguean con su usuario/contraseña,
suben los PDFs, hacen click en "Generar" y descargan la imagen.

---

## Cambiar contraseñas (cuando sea necesario)

1. Entrar a render.com → tu servicio → **"Environment"**
2. Editar la variable `USERS`
3. Click **"Save Changes"** → la app se reinicia automáticamente

---

## Plan gratuito de Render

- La app se "duerme" después de 15 minutos sin uso
- La primera vez que alguien entra después de un período sin uso, 
  tarda ~30 segundos en "despertar"
- Para uso diario no es problema — después del primer acceso del día, 
  responde normal
- Si quieren que esté siempre activa, el plan Starter cuesta ~USD 7/mes

---

*Creado por Andi para Francisco — Quick Seguro 2024*
