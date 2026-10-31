# Subir Neo a GitHub desde Windows

Estas instrucciones son para crear un repositorio nuevo con el código que
está en la carpeta `Neo_Conversacional`. La cuenta GitHub conectada es
**KeniChris**. El nombre sugerido para el repositorio es `Neo_Conversacional`.

## Crear un repositorio vacío

1. Abre [github.com/new](https://github.com/new).
2. Pon `Neo_Conversacional` como nombre, o elige otro nombre disponible.
3. Elige la visibilidad que quieras para el trabajo del equipo.
4. Crea el repositorio vacío: deja sin seleccionar README, .gitignore y licencia.
   El proyecto ya contiene README y .gitignore.
5. Copia su dirección HTTPS. Si mantuviste el nombre sugerido, será
   `https://github.com/KeniChris/Neo_Conversacional.git`.

Si ya existe un repositorio para el equipo, usa su enlace y su historial en
lugar de seguir estas instrucciones de primer envío a uno vacío.

## Primer envío

Abre PowerShell en la carpeta que contiene `probar_choregraphe.py`,
`README.md` y `.gitignore`. Si mantienes la ubicación de la prueba:

```powershell
cd 'C:\Users\leysi\Downloads\Neo_Conversacional\Neo_Conversacional'
git --version
git init -b main
git add .
git status --short
```

En el estado verás los scripts, las políticas, la documentación y las pruebas.
`.venv_neo` y `__pycache__` quedan excluidos por `.gitignore`.

Después, para el repositorio vacío creado en el paso anterior:

```powershell
git commit -m 'Proyecto Neo: conversacion, vision y pruebas en Choregraphe'
git remote add origin https://github.com/KeniChris/Neo_Conversacional.git
git push -u origin main
```

Si elegiste otro nombre, cambia la URL por la que copiaste de GitHub.
Completa el acceso a GitHub si Git abre una ventana de autenticación.
La sesión de Codex y la autenticación de GitHub son configuraciones distintas.

## Si aparece un error

| Mensaje | Qué revisar |
| --- | --- |
| `git` no se reconoce | Instala Git para Windows desde su sitio oficial y abre una terminal nueva |
| `Author identity unknown` | Configura nombre y correo para este repositorio, según el bloque siguiente |
| `remote origin already exists` | Mira `git remote -v`; comprueba el destino antes de cambiarlo |
| `Repository not found` | Confirma que creaste el repositorio, la URL y la cuenta con acceso |
| `non-fast-forward` / `fetch first` | El remoto ya tiene historial; conserva ese historial y revisa cómo integrarlo |

Si Git pide identidad, utiliza tu nombre de autor y el correo verificado o
la dirección de GitHub para mantener privado el correo, que puedes consultar
en [Settings > Emails](https://github.com/settings/emails). Sustituye ambos
valores del ejemplo; la configuración se aplica solo a este repositorio:

```powershell
git config user.name 'TU_NOMBRE_DE_AUTOR'
git config user.email 'TU_CORREO_CONFIGURADO_EN_GITHUB'
git commit -m 'Proyecto Neo: conversacion, vision y pruebas en Choregraphe'
git push -u origin main
```

## Subir cambios posteriores

Desde la misma carpeta:

```powershell
git add .
git commit -m 'Describe el cambio que acabas de hacer'
git push
```

El compañero puede clonar el repositorio e instalar las dependencias siguiendo
el README. No necesita recibir el entorno virtual completo.

Referencia: [GitHub: subir código local mediante Git](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).
