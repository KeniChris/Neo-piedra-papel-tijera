import subprocess
import time

start = time.time()
try:
    # Llama al script en Python 2.7 con el comando
    result = subprocess.run(
        ["C:/Python27/python.exe", r"C:\Users\leysi\Downloads\Prueba_naoqui\prueba_naoqui.py"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print(f"Ejecutado: {result.stdout}")
        print(f"Argumentos: {result.args}")
    else:
        print(f"Error: {result.stderr}")
except Exception as e:
    print(f"Error ejecutando el comando: {e}")

end = time.time()
print(end-start)