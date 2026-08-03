#!/bin/bash

echo "🔍 Probando Acceso al Menú de Video..."
echo ""

# Prueba 1: Verificar si la app está corriendo
echo "1. Verificando si la aplicación está en ejecución..."
ps aux | grep "python.*app.py" | grep -v grep
if [ $? -eq 0 ]; then
    echo "✅ La aplicación está en ejecución"
else
    echo "❌ La aplicación NO está en ejecución"
    exit 1
fi

# Prueba 2: Verificar si el puerto 5000 está abierto
echo ""
echo "2. Verificando si el puerto 5000 está escuchando..."
lsof -i :5000 | head -2
if [ $? -eq 0 ]; then
    echo "✅ El puerto 5000 está abierto"
else
    echo "❌ El puerto 5000 NO está abierto"
    exit 1
fi

# Prueba 3: Probar página de login
echo ""
echo "3. Probando página de inicio de sesión..."
curl -s -I http://localhost:5000/login | head -1
if [ $? -eq 0 ]; then
    echo "✅ Página de inicio de sesión accesible"
else
    echo "❌ Página de inicio de sesión NO accesible"
fi

# Prueba 4: Iniciar sesión y obtener cookie de sesión
echo ""
echo "4. Probando inicio de sesión con credenciales de admin..."
COOKIE=$(curl -s -c - -X POST http://localhost:5000/login \
    -d "username=admin&password=admin" \
    | grep "session" | awk '{print $NF}')

if [ ! -z "$COOKIE" ]; then
    echo "✅ Inicio de sesión exitoso, se obtuvo la cookie de sesión"
    
    # Prueba 5: Acceder al streaming de video con autenticación
    echo ""
    echo "5. Probando flujo de video con autenticación..."
    curl -s -b "session=$COOKIE" http://localhost:5000/video_feed \
        --max-time 2 | head -c 100
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ ¡El flujo de video se está transmitiendo!"
    else
        echo ""
        echo "❌ Fallo en el flujo de video"
    fi
else
    echo "❌ Fallo al iniciar sesión - verifica las credenciales"
fi

echo ""
echo "===================================================="
echo "Accede a la aplicación en: http://192.168.1.223:5000"
echo "Usuario: admin"
echo "Contraseña: admin"
