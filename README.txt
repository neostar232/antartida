Voy a ir dejando acá, datos relevantes y otros no tanto

* Orden para arrancar la aplicación desde la consola:
flask --app ushuaia run --debug

* Usuarios y passwords
adm@ushuaia.com // pswdeadm
enc@usuahia.com // pswdeenc
pv1@@ushuaia.com // pswdepv1 -- Usuario del Bar
pv2@@ushuaia.com // pswdepv2 -- Usuario del Comedor
pv3@@ushuaia.com // pswdepv3 -- Usuario del Room Service

############################# Voy dejando acá las ultimas actualizaciones con fecha #############################
10/07
# Se configura la barra de navegación
# Se eliminaron las referencias a los archivos .map en *boostrap.*
# Se agregó .ico a fin de que no genere error en consola


09/07
# Se agrega la biblioteca 'Flask_Caching', a fin de no generar caché (pip install flask_caching)
# En la medida de lo posible, se reemplazaron los enlaces a librerías externas a archivos locales
# Se completan para los puntos de venta, las acciones de "Ropa.." y "Consulta..."
# Para "Ropa y Accesorios", el alcance llega hasta el registro en la cuenta del pasajero (no toca stock)
# Los consumos por pasajeros se muestran sólo si el pasajero realizó consumos y el trip esté abierto
# Se agrega el apartado de "Reimpresión..." por eventuales fallas en el momento de concretar el consumo
# Se eliminaron archivos de prueba


# 05/07
Acceso a través de http://127.0.0.1:5000/passengers/auth (chequear URL/puerto local)
Se modifica en login_passenger.html el logo (se coloca el del buque)


# 04/07/25
* Se agregó Blueprint para el front pasajeros auth_passengers
* Se agregaron varios html del front de pasajeros en /templates

## Login de pasajeros:
* Nuevo formulario y lógica para que los pasajeros puedan iniciar sesión con su email y contraseña. Al autenticarse, se guarda su ID y email en la sesión.

## Menú principal de pasajero:
* Pantalla con acceso rápido a las distintas categorías de productos y a la consulta de consumos personales.

## Consulta de consumos personales:
* Al hacer clic en “Consulta de Consumos”, el pasajero ve directamente una lista de todos sus consumos registrados, sin necesidad de seleccionar cabina ni usuario.
* Cada consumo muestra la fecha, el producto y el precio total.

## Seguridad:
* Solo el pasajero logueado puede ver sus propios consumos. Si no hay sesión activa, se redirige al login.

## Código modular:
* Todo el flujo de pasajeros está separado en un blueprint (auth_passengers) y en plantillas HTML específicas para cada pantalla.

19/06
# Se mueven las funciones de acceso y los archivos .html relacionados, a uan ubicación mas representativa
# 



17/06
# Se actualiza reportería: sólo aquellos reportes que referencian existencias
# Se concilia la totalidad del stock
# Se controlan y corrigen categorías y subcategorías de aproximadamente 50 productos (puede haber más)
# Se revisó el Listado de diferencias OC Vs. Recibido (por favor, chequear)



16/06
# Se agrega campo 'dt_last_update' a la tabla 'bt_product' dónde se verá reflejado el momento de actualización de
cada producto en particular o lote de productos, de corresponder (los productos que no tienen un valor mayor
a 0 en ese campo, es debido a que no se realizaron test con los mismos)
# Se modifican las funciones que impactan en el inventario, dónde intervienen productos que forman parte de la
preorden, a fin de que la misma indique la existencia de productos antes del cierre de la preorden
# Se modifica formulario de alta individual de pasajeros (marca de campo obligatorio)


14/06
# Se agrega campo 'q_stock' a la tabla 'bt_product' dónde se verá reflejada la existencia de cada producto
# Se ejecuta consulta que actualiza el campo nombrado anteriormente (para almacenes con id <= 11)
# Se modifican las distintas funciones dónde interviene la tabla temporal 'nsv' en 'stock.py'
# Se renombra la base 'ushuaia_desa.db' a 'usuahia.db', volviendo a la nomenclatura original
# Se modifican los campos obligatorios de la tabla 'bt_passenger'


07/06
# Se amplía el ancho del contenedor del sitio, para no scrollear al acceder a las nuevas secciones
# Se modifica tabla de pasajeros (falta la generación automática y cifrada de psw)
# PENDING: pasar a pestañas el acceso del Administrador a los menúes


31/05
# Los pendings del 28/05 ya están listos para testearse; sólo valida en el usuario, no en el servidor

28/05
* PENDING Se modifica move_stock.html para que haga la comprobación sobre las cantidades de las transferencias
* PENDING Actualización del stock remanente acumulado

23/05
* Se modifica el nombre del Almacén "Bar": ahora es "Bar / Pto. de Venta"
* Se crea un nuevo almacén "Ventas", que hará el collect de las descargas del Almacén del primer punto
* No se considera la mas fecha de vencimiento en las transferencias entre depositos, por la falta de este dato
* El dato antes mencionado, junto al lote, tampoco se envían al formulario
* En el form, se ve el acumulado de existencias, luego el programa aplica el método FIFO

18/05
* Se reemplaza temporalmente, la bd normalmente utilizada por la version "_desa"
* Hay elementos para eliminar, los archuvos que componen la app van a ir variando constantemente
* Se crearon 3 nuevos usuarios/psw:
pv1@ushuaia.com/pswdepv1
pv2@ushuaia.com/pswdepv2
pv3@ushuaia.com/pswdepv3

y que corresponden, respectivamente a:
Usuario de Bar
Usuario del Comedor
Usuario del Room Service

Se modifican las formas de tratar las fechas: instalar pytz si es que no está instalado


11/09
Instalar numpy (si es que no está instalado ya)
*** CORREGIDO
El formulario de transferencias está terminado, pero aleatoriamente, acepta descargas mayores a las existencias
(hay un if que jode en la última función)
***
Se crea tabla de stock, falta hacer falta realizar la accion que incorpora la carga de las compras
El listado de disponibilidad está OK, con los valores que toma de la tabla de stock correspondiente
Se crean 2 depósitos nuevos:
* Consumos: para aquellos productos que no pasan por cocina (por ejemplo, shampoo, entre otros. Ya cuenta
con su respectivo reporte) 
* Rotura/Vencimiento/Gentileza : dónde se agrupan las bajas por esos motivos.
Respecto de éste último, resta hacer el form correspondiente

Falta cambiar el origen de datos de algunos reportes


Instalar openpyxl

13/08
Corregí el error ejecutando desde el terminal lo siguiente (XX es la versión de python):
sudo rm /usr/lib/python3.XX/EXTERNALLY-MANAGED

werkzeug

Buscar archivo de flujo en la carpeta 'static/flujo_OC.pdf' (después lo elimino)

10/08
Instalar librería para generar pdf's
pip install Flask-WeasyPrint

26/07
Empecé a trabajar sobre el formulario de pedido; falta todo lo relacionado a las variables de session
para guardar temporalmente los datos y luego subirlo a tablas de la app

21/07
Se modifica acceso a panel de acuerdo al nivel indicado en el rol de usuario
Los usuarios con rol 1 (Administrador), acceden al panel completo
Los restantes usuarios, acceden al panel que contiene una visión operativa
Por ahora los paneles se replican agregando o quitando elementos
En desarrollo:
Estoy tratando de agregar el cron que actualice a diario las cotizaciones: instalate Advanced Python Scheduler
pip install apscheduler

14/07
Se ingestan registros en diversas tablas
Se crean tablas temporales que ayudaran a ingresar datos masivamente mediante archivos (sin uso de forms)
Deben dropearse antes de llegar a la version final


02/07
Se crean 2 tablas: cotizaciones y sesiones.
De las sesiones se registran 2 momentos: al ingresar y al salir.
Por eso es necesario hacer click en log out al dejar de operar. Crear hábito.
La tabla de cotizaciones aún no está lista, tengo que modificar los objetos que la referencian.

###########################################################################################################

*** Queries Varias (algunas las encontras dentro de los .py, esto es para ejecutarlas en la base) ***

/* Listado de productos */
SELECT
	b.id_product AS cod_producto,
	s.tx_subcategory AS subcategoria,    
	b.tx_product AS desc_producto,
    c.tx_category AS categoria,
	u.tx_unity AS presentacion,  
    b.num_reorder_point AS punto_repedido
FROM bt_product b INNER JOIN lkp_categories c
ON b.id_category = c.id_category
INNER JOIN lkp_subcategories s
ON b.id_subcategory = s.id_subcategory
INNER JOIN lkp_units u
ON b.id_unity = u.id_unity
WHERE b.flag_ctrl = 1;

/* Listado de productos en stock */
SELECT
    b.id_product AS cod_producto,
    s.tx_subcategory AS subcategoria,    
    b.tx_product AS desc_producto,
    -- c.tx_category AS categoria,
    u.tx_unity AS presentacion,  
    b.num_reorder_point AS punto_repedido,
    SUM(p.q_in) - SUM(p.q_out) AS existencias
FROM bt_product b INNER JOIN lkp_categories c
ON b.id_category = c.id_category
INNER JOIN lkp_subcategories s
ON b.id_subcategory = s.id_subcategory
INNER JOIN lkp_units u
ON b.id_unity = u.id_unity
INNER JOIN bt_in_out_prods p
ON b.id_product = p.id_product
WHERE b.flag_ctrl = 1
GROUP BY 1, 2, 3, 4, 5;

/* Existencias */
SELECT
    b.id_product AS cod_producto,
    s.tx_subcategory AS subcategoria,    
    b.tx_product ||' - ' || u.tx_unity AS producto,
    SUM(p.q_in) - SUM(p.q_out) AS existencias,
    w.tx_warehouse
FROM bt_product b INNER JOIN lkp_categories c
ON b.id_category = c.id_category
INNER JOIN lkp_subcategories s
ON b.id_subcategory = s.id_subcategory
INNER JOIN lkp_units u
ON b.id_unity = u.id_unity
INNER JOIN bt_in_out_prods p
ON b.id_product = p.id_product
INNER JOIN lkp_warehouse w
ON p.id_warehouse = w.id_warehouse
WHERE b.flag_ctrl = 1
GROUP BY 1, 2, 3, 5;

/* Existencias V2 (a modificar por el hardcodeo de los nombres de los almacenes) */
SELECT
    b.id_product AS cod_producto,
    s.tx_subcategory ||': '|| b.tx_product ||' (' || u.tx_unity ||')' AS producto,
    IFNULL(SUM(CASE WHEN tx_warehouse = 'Almacén 1' THEN (p.q_in - p.q_out) END), 0) AS "Almacén 1",
    IFNULL(SUM(CASE WHEN tx_warehouse = 'Almacén 2' THEN (p.q_in - p.q_out) END), 0) AS "Almacén 2",
    IFNULL(SUM(CASE WHEN tx_warehouse = 'Almacén 3' THEN (p.q_in - p.q_out) END), 0) AS "Almacén 3",
    IFNULL(SUM(CASE WHEN tx_warehouse = 'Almacén 4' THEN (p.q_in - p.q_out) END), 0) AS "Almacén 4",
    IFNULL(SUM(CASE WHEN tx_warehouse = 'Almacén 5' THEN (p.q_in - p.q_out) END), 0) AS "Almacén 5",
    IFNULL(SUM(CASE WHEN tx_warehouse = 'Almacén 6' THEN (p.q_in - p.q_out) END), 0) AS "Almacén 6",
    IFNULL(SUM(CASE WHEN tx_warehouse = 'Almacén 7' THEN (p.q_in - p.q_out) END), 0) AS "Almacén 7",
    IFNULL(SUM(CASE WHEN tx_warehouse = 'Almacén 8' THEN (p.q_in - p.q_out) END), 0) AS "Almacén 8",
    IFNULL(SUM(CASE WHEN tx_warehouse = 'Almacén 9' THEN (p.q_in - p.q_out) END), 0) AS "Almacén 9"    
FROM bt_product b INNER JOIN lkp_categories c
ON b.id_category = c.id_category
INNER JOIN lkp_subcategories s
ON b.id_subcategory = s.id_subcategory
INNER JOIN lkp_units u
ON b.id_unity = u.id_unity
INNER JOIN bt_in_out_prods p
ON b.id_product = p.id_product
INNER JOIN lkp_warehouse w
ON p.id_warehouse = w.id_warehouse
WHERE b.flag_ctrl = 1
GROUP BY 1, 2
ORDER BY 2, 1;



/* Agregado de productos (el ejemplo tiene datos reales ya insertados) */
INSERT INTO bt_product(tx_product, id_category, id_subcategory, id_unity, num_reorder_point, flag_ctrl)
VALUES("Chandon Brut Nature", "1", "5", "12", "6", "1"),
("Chandon Demi Sec", "1", "5", "12", "6", "1"),
("Chandon Extra Brut", "1", "5", "12", "6", "1"),
("Federico de Alvear Extra Brut", "1", "5", "12", "6", "1");


/* Agregado de stock (el ejemplo tiene datos reales ya insertados) */
INSERT INTO bt_in_out_prods(dt_movement, cuit_supplier, id_product, dt_expiry, id_warehouse, q_in, id_user)
VALUES("2024-06-01","11111111111","24","2024-12-31","1","30","1"),
("2024-06-01","11111111111","25","2024-12-31","1","12","1"),
("2024-06-01","11111111111","26","2024-12-31","1","6","1");

/* Creación de trigger para registrar cambios de precios - El equivalente para productos está en la base */
CREATE TRIGGER add_price AFTER INSERT ON bt_prices
BEGIN
    INSERT INTO logs(dt_log, id_object, type_event)
    VALUES(datetime('now'), 'bt_prices', 'INSERT');
    UPDATE logs SET id_user =
        (SELECT id_user FROM
            (SELECT
                MAX(id_price) AS mxm,
                id_user
            FROM bt_prices
            GROUP BY 2
             )
         )
     WHERE id_user IS NULL;
END;
