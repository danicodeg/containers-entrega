#Cómo instalar el módulo:

1. Tener una instalación de Odoo 17 Community conectada a PostgreSQL.
2. Descargar el repositorio. Guárdelo en cualquier carpeta de su equipo. Al abrir lo que descargó, verá una carpeta llamada containers. En el comando de instalación, agregue a --addons-path la ruta de la carpeta que contiene containers, junto con las rutas que ya usa Odoo.
3. En PostgreSQL, crear una base vacía llamada `odoo_entrega_test`. Seleccionar como propietario el usuario de PostgreSQL que usa Odoo. En esa misma base, ejecutar esta consulta desde pgAdmin:

   ```sql
   CREATE EXTENSION IF NOT EXISTS btree_gist;
   ```

   Esta extensión permite que el módulo valide que los períodos de uso de un mismo contenedor no se crucen.

4. Abrir la terminal en la carpeta `odoo`, donde está `odoo-bin`, y activar el entorno de Python de Odoo. Ejecutar este comando en una sola línea, reemplazando `HOST`, `PUERTO`, `USUARIO` y `CONTRASEÑA` por los datos de conexión de su PostgreSQL:

   ```powershell
   python odoo-bin --db_host=HOST --db_port=PUERTO -r USUARIO -w "CONTRASEÑA" --addons-path="addons,RUTA_DEL_REPOSITORIO" -d odoo_entrega_test -i containers
   ```

5. Dejar la terminal abierta. Cuando Odoo termine de cargar, abrir (http://localhost:8069/web?db=odoo_entrega_test). En Ajustes>Usuarios y compañías>Usuarios, asignar al usuario de prueba los grupos Operaciones y Facturación. Guardar los cambios, recargar la página y abrir Control de contenedores desde el menú.

Modelo de datos:
Para hacer el módulo, primero organicé las carpetas. En models dejé los campos, las relaciones y los cálculos. En views puse lo que se muestra en Odoo, como los formularios, las listas y los filtros. También usé security para los permisos de Operaciones y Facturación, y tests para las pruebas del cálculo de demoras.
En la carpeta models hice cuatro archivos. En customer_condition.py coloqué las condiciones que se necesitaban para cada cliente, como los días libres adicionales y el porcentaje de administración. En tariff.py coloqué las tarifas de las navieras y los tramos que se usan para calcular el cobro. container.py fue el archivo más largo porque ahí reuní lo del BL y sus contenedores, con las fechas, los estados, las validaciones y el cálculo de la demora. 
Por último, en container_correction.py dejé las solicitudes para corregir la fecha de devolución cuando el contenedor ya se facturó.
En models/__init__.py importé los cuatro archivos para que Odoo cargue los modelos. Para relacionar el BL con los contenedores usé Many2one en el contenedor, porque cada registro de contenedor pertenece a un BL, y One2many en el BL, porque un BL puede tener varios contenedores. Con esa relación pude mostrar en el formulario del BL una tabla con sus contenedores y manejar las fechas y el estado de cada uno.

Contradicciones del caso y decisiones que tomé:
Desde qué día se empieza a contar: Jorge contaba desde el día siguiente a la descarga, pero en la guía se indica que en estos casos se sigue lo que dice el contrato. Por eso tomé el día de la descarga como el día 1. Después se restan los días libres y, si quedan días de demora, se calcula el cobro por tramos.
Una fecha de descarga para todo el BL: Marcela normalmente registra los contenedores con la misma fecha, aunque algunos se pueden descargar otro día. Por eso dejé una fecha general en el BL y una fecha particular opcional en cada contenedor. Si se llena la fecha particular, esa es la que se usa para el cálculo.
Corregir una devolución después de facturar: Marcela podía recibir tarde la fecha correcta y Jorge necesitaba conservar lo que ya había facturado. Por eso puse el botón de corrección en cada contenedor facturado. Operaciones registra la nueva fecha y el motivo, y Facturación aprueba o rechaza la solicitud desde Correcciones. Cuando se aprueba, la fecha corregida aparece al lado de la fecha original en el BL. 
La solicitud también muestra el importe recalculado y la diferencia, y el contenedor conserva el cálculo con el que se facturó.
Quién puede modificar las tarifas: Patricia quería limitar los cambios de tarifas. Por eso creé los grupos de Operaciones y Facturación. Operaciones puede consultar las tarifas y registrar los contenedores. Facturación puede gestionar las tarifas, marcar un contenedor como facturado y revisar las correcciones.
Porcentaje de administración: Dejé el 10 % como valor predeterminado y el porcentaje editable por cliente para manejar acuerdos como el del 5 %. Los días libres extra se configuran por cliente y naviera, porque el acuerdo puede cambiar según la naviera.

Cómo resolví la corrección de fechas de Marcela:
Lo que entendí del caso fue que Marcela podía recibir tarde la fecha real de devolución, incluso cuando Jorge ya había facturado. Jorge necesitaba conservar la fecha y el importe que había usado para facturar, pero Marcela también necesitaba dejar registrada la fecha correcta.
Al principio pensé en poner el botón de corrección arriba del BL, porque cuando trabajaba con Odoo Studio en el modulo de inventario se veía un botón de devolución de traslados, entonces pensé en hacer lo mismo pero luego vi que en un mismo BL puede haber un contenedor que sigue afuera, otro que ya se devolvió y otro que ya se facturó, por lo que el botón general no servía. Por eso puse el botón en la fila de cada contenedor facturado, porque la corrección se hace sobre ese contenedor en particular.
El flujo que escogí fue que Marcela, desde el BL, pulse "solicitar corrección" en la fila del contenedor. Ahí puede escribir la fecha de devolución correcta, explicar el motivo y adjuntar el EIR si lo tiene. La solicitud queda pendiente en la pestaña Correcciones, donde Jorge, desde Facturación, puede aprobarla o rechazarla.
También quise que Marcela pudiera ver el resultado desde el mismo BL. Por eso agregué una columna al lado de la fecha de devolución original. Cuando Jorge aprueba la solicitud, la fecha corregida aparece automáticamente en esa columna. Si la rechaza, en el BL se sigue mostrando la última fecha corregida que se haya aprobado, si existe.
Así, al abrir el BL se puede ver qué fecha se usó para facturar y cuál fue la fecha corregida. En Correcciones queda el importe recalculado y la diferencia para el cliente, mientras el contenedor conserva el estado Facturado y el importe original.

Cómo trabajé los grupos y los filtros:
Cuando trabajaba con Odoo Studio, cuando necesitaba definir quién podía acceder a algo, entraba a la parte técnica de Odoo y configuraba los permisos desde la interfaz. Por ejemplo, si tenía un grupo de empleados, usaba las reglas de registro y sus dominios para definir qué registros podían ver. En esta prueba fue nuevo para mí configurar los grupos y los permisos desde el código. En la carpeta “security” creé los grupos de Operaciones y Facturación y definí qué podía hacer cada uno. 
Operaciones puede consultar las tarifas y registrar los contenedores, y Facturación puede modificar las tarifas y aprobar o rechazar las correcciones. Así cada persona puede trabajar con su propio usuario y con los permisos que necesita.
Para los filtros, en Odoo Studio yo usaba el buscador. Escogía el campo, ponía una condición como “es igual a” y después seleccionaba el valor. Si quería buscar registros asignados a alguien, escogía el campo “Asignado a” y seleccionaba a la persona. Lo nuevo para mí fue usar esa misma lógica en código y dejar listos los tres filtros que pedía Marcela. Por ejemplo, para mostrar los contenedores vencidos que siguen afuera, puse dos condiciones en el dominio: que el estado sea Afuera y que el último día libre sea anterior a hoy.


Preguntas que le haría al cliente antes de salir a producción:
¿El flujo desde que se registra un BL hasta que se factura el contenedor funciona como lo necesitan?
¿Les hace falta algún campo en el BL, en el contenedor o en la solicitud de corrección?
¿Está bien que Operaciones solicite la corrección de una fecha y que Facturación la apruebe o la rechace?
¿Los permisos de Operaciones y Facturación corresponden a lo que hace cada persona? ¿Alguien más debería poder consultar o modificar las tarifas?
¿Necesitan otros filtros para las diferentes pestañas?

Resultados casos 6 a 9:
Primero creé el documento BL del caso 6 y coloqué la misma información que aparece en la guía. 
Después fui a Tarifas y creé la tarifa de Atlántico para el contenedor 20DV, con 7 días libres. Según la tabla de la guía, esta tarifa tiene tres tramos. Del día 1 al 5 se cobran USD 35 por día, del 6 al 10 se cobran USD 70 y desde el día 11 se cobran USD 110. 
En el último tramo coloqué "0" en el campo "hasta" porque en el módulo ese valor indica que el tramo sigue desde el día 11 en adelante.
Después guardé la tarifa y le di clic a Comprobar tramos. Volví al BL y ahí pude ver el cálculo que hizo el módulo con las fechas que había ingresado. Para los casos 7 y 8 usé esa misma tarifa.
Caso 6: El contenedor estuvo 7 días afuera y tenía 7 días libres. Como se devolvió el último día libre, quedó con 0 días de demora y el cobro fue de USD 0,00.
Caso 7: El contenedor estuvo 8 días afuera. Al quitar los 7 días libres, quedó 1 día de demora. Como ese día entra en el primer tramo, la naviera cobra USD 35,00 y al cliente se le cobran USD 38,50 con el 10 % de administración.
Caso 8: Coloqué la misma fecha para la descarga y la devolución. Ese día cuenta como 1 día afuera. Como tenía 7 días libres, quedó con 0 días de demora y el cobro fue de USD 0,00.
Caso 9: En la guía dice que Mar del Sur Line no tiene tarifa para el contenedor 40RF, así que dejé ese caso sin tarifa. En la columna Aviso de cálculo, aparece el mensaje "falta una tarifa para esta naviera, tipo y fecha de descarga".

Errores excel:
En la fila 2, el contenedor está mal escrito natu 508163 4, Odoo mostró el popup que debe ser con el formato ISO 6346. Al ingresarlo como NATU5081634, fue válido. El tipo también viene como 20', así que al registrarlo solo se puede 20DV.
En la fila 3, el tipo aparece 40 dv y la fecha de devolución solo como 15-jul, asi no se puede ingresar a Odoo. 
La fila 4 y 5 el contenedor es el mismo, cuando se ingresó odoo no permite ingresar el segundo registro avisa que el contenedor ya está registrado.
En la fila 6, al intentar guardar el contenedor con ese numero apareció el popup indicando que el numero esperado es el 6. 
En la fila 7, como no puede ser la fecha de devolución antes que la de descarga entonces odoo mostró el popup indicando que "La fecha de devolución no puede ser anterior a la de descarga"
En la fila 8, No está el cliente, en odoo se colocó que es obligatorio entonces si hay campos vacios y son obligatorios siempre aparece el aviso que falta un campo por llenar.

Lo que no alcancé a realizar:
Las funcionalidades de deseable y extra.
La que más me interesaba hacer era la alerta para Marcela para que le llegara cada mañana un aviso con los contenedores que vencen en los próximos dos días. Cuando trabajaba con Odoo Studio, ya había configurado acciones planificadas desde la interfaz. 
Por eso pensé que para este caso se podía usar la misma idea y programar una acción planificada que hiciera esa revisión cada mañana, sin embargo me faltaría estudiar más para saber como colocarla dentro del modelo.

Usé IA como apoyo en cada uno de los archivos porque realmente manejar con codigo los requisitos de esta prueba era nuevo para mí, sobre todo los cálculos de demora y cómo llevar al código lo que antes hacía desde la interfaz con Odoo Studio, pero a medida que iba avanzando, probaba los cambios en Odoo para entender qué hacía cada parte y revisar si el resultado coincidía con lo que pedía la guía. 
