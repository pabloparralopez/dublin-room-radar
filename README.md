# Dublin Room Radar · marzo 2027

Buscador de habitaciones privadas en Dublín para entrar **en marzo de 2027** y permanecer hasta al menos el **30 de junio de 2027**. Presupuesto ideal: **600–1.000 €/mes**, con excepciones justificadas.

**Ubicación:** importa la conexión real a **Parnell Street y O'Connell Street**, en particular la línea verde del Luas y los autobuses directos. Se incluyen todos los distritos, también **D9 y D4**, sin exclusiones automáticas por código postal.

## Publicar la página

1. Ir a **Settings → Pages** de este repositorio.
2. En **Build and deployment → Source**, seleccionar **GitHub Actions**.
3. Ir a **Actions → Actualizar y publicar Dublin Room Radar → Run workflow** y ejecutar.
4. Tras terminar correctamente, abrir la URL del despliegue. URL prevista (no confirmada activa): https://pabloparralopez.github.io/dublin-room-radar/

GitHub Actions comprueba diariamente alrededor de las **08:00 hora de Dublín**. GitHub puede retrasar las ejecuciones programadas.

## Funcionamiento y límites

La web ofrece enlaces originales, filtros de fecha y precio, búsqueda por zona, clasificación y favoritos guardados **solo en el navegador**. Los tres anuncios iniciales son **históricos y deben reconfirmarse**, no reservas.

El escáner experimental consulta páginas de **Rooms in Dublin, Daft Sharing, Rent.ie y MyHome Share**, únicamente si su robots.txt lo permite. Muchos portales bloquean automatizaciones, emplean JavaScript o requieren autenticación: **no se garantiza cobertura completa ni disponibilidad en tiempo real**. Si no consigue leer una fuente, informa de que falló, sin concluir que no hay habitaciones. **HostingPower, Roomgo y Roomies son enlaces de revisión manual**, no integraciones completas. La tarea diaria de ChatGPT es independiente de este código.

**Estados:** «Marzo anunciado» solo indica que una ficha publica esa fecha; no que esté confirmado por un propietario. «Pendiente» significa que falta verificar la fecha. Ninguna reserva, contacto o pago se realiza desde esta aplicación.

## Prueba local

Instalar Python 3.12+ y ejecutar:

```bash
python -m pip install -r requirements.txt
python radar.py --dry-run
python radar.py
python -m http.server 8000
```

Abrir http://localhost:8000.

## Archivos

- `config.json`: criterios.
- `data/listings.json`: anuncios.
- `data/sources.json`: resultados de la última consulta.
- `.github/workflows/scan.yml`: tarea programada y publicación.

Para convertir alquiler semanal a mensual usar **precio × 52/12**. Verificar fianza, facturas, comisiones y plazo con el anunciante. No subir contraseñas ni documentos personales: el repositorio es público.
