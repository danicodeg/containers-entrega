from datetime import timedelta
import re
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

ISO_LETTER_VALUES = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    [value for value in range(10, 39) if value % 11 != 0],
))
class BillOfLading(models.Model):
    _name = "containers.bill.of.lading"
    _description = "Bill of Lading"

    name = fields.Char(string="Número de BL", required=True)
    customer_id = fields.Many2one(
        "res.partner", string="Cliente", required=True
    )
    shipping_line_id = fields.Many2one(
        "res.partner", string="Naviera", required=True
    )
    discharge_date = fields.Date(string="Fecha de descarga general")
    container_ids = fields.One2many(
        "containers.container", "bill_of_lading_id", string="Contenedores"
    )
#llama el metodo cuando se guarde la fecha general 
    @api.constrains("discharge_date")
    def _check_container_return_dates(self):
        self.mapped("container_ids")._check_return_date() 

#se usa esta funcion para que no se pueda cambiar la fecha de descarga general si ya hay contenedores facturados
    def write(self, vals):
        protected_fields = {"customer_id", "shipping_line_id", "discharge_date"}
        if protected_fields.intersection(vals) and any(
            self.mapped("container_ids.invoiced_at")
        ):
            raise ValidationError(
                "El BL tiene contenedores facturados. "
                "Estos datos requieren una corrección autorizada."
            )

        return super().write(vals)


class Container(models.Model):
    _name = "containers.container"
    _description = "Container"

#regla para decir a postgres que no pueden ser los mismos periodos de descarga y devolucion de un contenedor
    _sql_constraints = [
        (
            "no_overlapping_periods",
            """
            EXCLUDE USING gist (
                name WITH =,
                daterange(discharge_date, return_date, '[]') WITH &&
            )
            WHERE (
                discharge_date IS NOT NULL
                AND (return_date IS NULL OR return_date >= discharge_date)
            )
            """,
            "Este contenedor ya está registrado en un período que se cruza con estas fechas.",
        ),
    ]
    #campos del contenedor en el bl
    name = fields.Char(string="Número de contenedor", required=True)
    bill_of_lading_id = fields.Many2one(
        "containers.bill.of.lading",
        string="BL",
        required=True,
        ondelete="restrict",
    )
    container_type = fields.Selection(
        [
            ("20DV", "20DV"),
            ("40DV", "40DV"),
            ("40HC", "40HC"),
            ("40RF", "40RF"),
        ],
        string="Tipo de contenedor",
        required=True,
    )
    discharge_date_override = fields.Date(string="Fecha de descarga particular")
    discharge_date = fields.Date(
        string="Fecha de descarga efectiva",
        compute="_compute_discharge_date",
        store=True,
    )
    return_date = fields.Date(string="Fecha de devolución")
    
    free_time_end_date = fields.Date(
        string="Último día libre", 
        compute="_compute_free_time_end_date", 
        search="_search_free_time_end_date",
    )
    
    correction_ids = fields.One2many(
        "containers.container.correction",
        "container_id",
        string="Solicitudes de corrección",
    )
    approved_return_date = fields.Date(
        string="Fecha de devolución corregida",
        compute="_compute_approved_return_date",
    )
    eir_file = fields.Binary(string="Comprobante EIR", attachment=True)
    eir_filename = fields.Char(string="Nombre del archivo EIR")

    invoiced_at = fields.Datetime(
        string="Fecha de facturación",
        readonly=True,
        copy=False,
    )

    invoiced_values = fields.Json( 
        string="Cálculo al facturar",
        readonly=True,
        copy=False, #hace que no se copie el campo al duplicar el registro
    )

    state = fields.Selection(
        [
            ("pending", "Pendiente de descarga"),
            ("outside", "Afuera"),
            ("returned", "Devuelto"),
            ("invoiced", "Facturado"),
        ],
        string="Estado",
        compute="_compute_state",
        store=True,
    )

    days_outside = fields.Integer(
        string="Días afuera",
        compute="_compute_demurrage",
    )

    free_days = fields.Integer(
        string="Días libres",
        compute="_compute_demurrage",
    )

    delay_days = fields.Integer(
        string="Días de demora",
        compute="_compute_demurrage",
    )

    shipping_amount_usd = fields.Float(
        string="Naviera (USD)",
        compute="_compute_demurrage",
        digits=(16, 2),
    )

    customer_amount_usd = fields.Float(
        string="Cliente (USD)",
        compute="_compute_demurrage",
        digits=(16, 2),
    )

    is_estimate = fields.Boolean(
        string="Estimado",
        compute="_compute_demurrage",
    )

    calculation_ok = fields.Boolean(
        compute="_compute_demurrage",
    )

    calculation_message = fields.Char(
        string="Aviso de cálculo",
        compute="_compute_demurrage",
    )
    @api.depends("discharge_date", "return_date", "invoiced_at")
   #vuelva a calcular el estado si esos campos cambian  y segun el valor de esos campos se asigna un estado
    def _compute_state(self):
        for container in self:
            if container.invoiced_at:
                container.state = "invoiced"
            elif container.return_date:
                container.state = "returned"
            elif container.discharge_date:
                container.state = "outside"
            else:
                container.state = "pending"
                
    @api.depends(
        "correction_ids.state",
        "correction_ids.reviewed_at",
        "correction_ids.corrected_return_date",
    )
    
    def _compute_approved_return_date(self):
        for container in self:
            approved = container.correction_ids.filtered(
                lambda correction: correction.state == "approved"
            )
            latest = approved.sorted(
                key=lambda correction: (
                    correction.reviewed_at or correction.create_date,
                    correction.id,
                ),
                reverse=True,
            )[:1]
            container.approved_return_date = latest.corrected_return_date 
            
    @api.depends("discharge_date", "free_days", "calculation_ok")
#para crear los filtros que en odoo se ven en la parte superior de la vista de lista

    def _compute_free_time_end_date(self):
        for container in self:
            if container.discharge_date and container.calculation_ok:
                container.free_time_end_date = (
                    container.discharge_date
                    + timedelta(days=container.free_days - 1)
                )
            else:
                container.free_time_end_date = False
    def _search_free_time_end_date(self, operator, value):
        comparison_date = fields.Date.to_date(value)
        candidates = self.search([
            ("state", "=", "outside"),
            ("discharge_date", "!=", False),
        ])
        matches = candidates.filtered_domain([
            ("free_time_end_date", operator, comparison_date),
        ])
        return [("id", "in", matches.ids)]    
    
    def action_open_correction(self):
        self.ensure_one()
        self.check_access_rights("read")
        self.check_access_rule("read")

        if not self.env.user.has_group("containers.group_container_operations"):
            raise AccessError("Solo Operaciones puede solicitar una corrección.")

        if self.state != "invoiced":
            raise ValidationError(
                "Solo puedes solicitar correcciones para contenedores facturados."
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Solicitar corrección",
            "res_model": "containers.container.correction",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                **self.env.context,
                "default_container_id": self.id,
                "from_container": True,
            },
        }
    def action_mark_invoiced(self):
        self.ensure_one()
        self.check_access_rights("read")
        self.check_access_rule("read")

        if not self.env.user.has_group("containers.group_container_billing"):
            raise AccessError("Solo el grupo de Facturación puede marcar como facturado.")

        if self.state != "returned":
            raise ValidationError("Solo se puede facturar un contenedor devuelto.")
#calcula la demora
        values = self._get_demurrage_values()
        super(Container, self.sudo()).write({
            "invoiced_at": fields.Datetime.now(),
            "invoiced_values": values,
        })
        return True
#no permite que se pueda crear un contenedor con los campos de facturacion ya llenos
    @api.model_create_multi
    def create(self, vals_list):
        protected_fields = {"invoiced_at", "invoiced_values"}
        if any(protected_fields.intersection(vals) for vals in vals_list):
            raise ValidationError("Usa el botón Marcar como facturado.")

        return super().create(vals_list)
#aplica dos reglas dde seguridad para que no se pueda cambiar la fecha de facturacion ni los valores de facturacion y que si se quiere cambiar algun campo protegido de un contenedor facturado se tenga que hacer una correccion
    def write(self, vals):
        if {"invoiced_at", "invoiced_values"}.intersection(vals):
            raise ValidationError("Usa el botón Marcar como facturado.")

        protected_fields = {
            "name",
            "bill_of_lading_id",
            "container_type",
            "discharge_date_override",
            "return_date",
        }
        if protected_fields.intersection(vals) and any(self.mapped("invoiced_at")):
            raise ValidationError(
                "Los datos de un contenedor facturado requieren una corrección autorizada."
            )

        return super().write(vals)
#calculo para la demora y el cobro al cliente y a la naviera
    def _get_demurrage_values(self, cutoff_date=None, corrected_return_date=None):
        self.ensure_one()

        bl = self.bill_of_lading_id
        discharge_date = self.discharge_date

        if not discharge_date or not bl.customer_id or not bl.shipping_line_id:
            raise ValidationError(
                "Completa cliente, naviera y fecha de descarga para calcular."
            )
#hasta que fecha que fecha de corte o fecha de devolucion corregida se va a calcular la demora
        cutoff_date = (
            fields.Date.to_date(cutoff_date)
            if cutoff_date
            else fields.Date.context_today(self)
        )
    #escoge el primer valor que exista
        end_date = corrected_return_date or self.return_date or cutoff_date
    #no se puede si la fecha de devolucion es menor a la fecha de descarga
        if end_date < discharge_date:
            raise ValidationError(
                "La fecha de corte o devolución es anterior a la descarga."
            )
    #me busca la tarifa que corresponda 
        tariff = self.env["containers.tariff"].search(
            [
                ("shipping_line_id", "=", bl.shipping_line_id.id),
                ("container_type", "=", self.container_type),
                ("valid_from", "<=", discharge_date),
                "|",
                ("valid_to", "=", False),
                ("valid_to", ">=", discharge_date),
            ]
        )

        if not tariff:
            raise ValidationError(
                "Falta una tarifa para esta naviera, tipo y fecha de descarga."
            )

        if len(tariff) != 1:
            raise ValidationError(
                "Hay varias tarifas aplicables. Revisa sus vigencias."
            )
#si hay dias extra, condiciones del cliente se suman a los dias libres 
        condition = self.env["containers.customer.condition"].search(
            [
                ("customer_id", "=", bl.customer_id.id),
                ("shipping_line_id", "=", bl.shipping_line_id.id),
            ],
            limit=1,
        )
        extra_days = condition.extra_free_days if condition else 0 #si tiene condicion se suma sino es 0
        days_outside = (end_date - discharge_date).days + 1
        free_days = tariff.free_days + extra_days
        delay_days = max(0, days_outside - free_days)

        usd = self.env.ref("base.USD")
        shipping_amount = usd.round(
            tariff._calculate_demurrage(delay_days)
        )
#calcula el cobro al cliente segun el porcentaje de administracion
        percentage = bl.customer_id.administration_percentage
        customer_amount = usd.round(
            shipping_amount * (1 + percentage / 100)
        )
#me trae los resultados de los calculos y si e s estimado o no
        return {
            "days_outside": days_outside,
            "free_days": free_days,
            "delay_days": delay_days,
            "shipping_amount_usd": shipping_amount,
            "customer_amount_usd": customer_amount,
            "is_estimate": not bool(self.return_date),
        }
#si cambia los campos se vuelve a calcular
    @api.depends(
        "invoiced_values",
        "discharge_date",
        "return_date",
        "container_type",
        "bill_of_lading_id.customer_id",
        "bill_of_lading_id.shipping_line_id",
        "bill_of_lading_id.customer_id.administration_percentage",
    )
#si hay filtross, o si hay diferente zona horaria vuelve a  a calcular 
    @api.depends_context("demurrage_cutoff_date", "tz")
    def _compute_demurrage(self):
        for container in self:
            values = {
                "days_outside": 0,
                "free_days": 0,
                "delay_days": 0,
                "shipping_amount_usd": 0.0,
                "customer_amount_usd": 0.0,
                "is_estimate": not bool(container.return_date),
                "calculation_ok": False,
                "calculation_message": False,
            }

            if container.invoiced_values:
                values.update(container.invoiced_values)
                values["calculation_ok"] = True
            else:
                try:
                    calculated_values = container._get_demurrage_values(
                        cutoff_date=self.env.context.get("demurrage_cutoff_date")
                    )
                except ValidationError as error:
                    values["calculation_message"] = str(error)
                else:
                    values.update(calculated_values)
                    values["calculation_ok"] = True

            container.update(values)

    @api.constrains("name")
    def _check_container_number(self):
        for container in self:
            number = container.name or ""

            if not re.fullmatch(r"[A-Z]{3}[UJZ][0-9]{7}", number): #verifica que esas 3 letras sean mayusculas y que sea la ultima y 7 digitos
                raise ValidationError(
                    "Escribe el número de contenedor en mayúsculas y sin espacios. "
                    "Debe tener 4 letras (la cuarta U, J o Z) y 7 dígitos."
                )

            total = 0 #es el acumulador de la suma de los valores de las letras y los digitos multiplicados por 2 elevado a la posicion del caracter
            for position, character in enumerate(number[:10]):
                value = (
                    int(character)
                    if character.isdigit()
                    else ISO_LETTER_VALUES[character] #si no entonces busque la equivalencia en el diccionario de letras a numeros
                )
                total += value * (2 ** position)
#divide la suma total entre 11 y luego el resultado entre 10 para obtener el digito de control esperado
            expected_digit = (total % 11) % 10 
            if int(number[-1]) != expected_digit: #si no coincide lance el error
                raise ValidationError(
                    f"El dígito de control de {number} es incorrecto. "
                    f"El dígito esperado es {expected_digit}."
                )

    @api.constrains("return_date", "discharge_date_override", "bill_of_lading_id")
    def _check_return_date(self):
        today = fields.Date.context_today(self)  

        for container in self:
            if not container.return_date:
                continue

            discharge_date = (
                container.discharge_date_override
                or container.bill_of_lading_id.discharge_date
            )

            if not discharge_date:
                raise ValidationError(
                    "Registra la fecha de descarga antes de registrar la devolución."
                )

            if container.return_date < discharge_date:
                raise ValidationError(
                    "La fecha de devolución no puede ser anterior a la de descarga."
                )

            if container.return_date > today:
                raise ValidationError(
                    "La fecha de devolución no puede ser futura."
                )

    @api.depends("discharge_date_override", "bill_of_lading_id.discharge_date")
    def _compute_discharge_date(self):
        for container in self:
            container.discharge_date = (
                container.discharge_date_override
                or container.bill_of_lading_id.discharge_date
            )
