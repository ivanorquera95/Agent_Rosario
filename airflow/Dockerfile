# La imagen oficial de Airflow ya trae el scheduler y el webserver.
# Encima se instalan las dependencias de los scripts del proyecto, que
# corren dentro del mismo contenedor.
FROM apache/airflow:2.10.5-python3.12

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt