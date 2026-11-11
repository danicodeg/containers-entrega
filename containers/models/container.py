import re
from odoo import api, fields, models
from odoo.exceptions import ValidationError

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
    
    @api.constrains("discharge_date")
    def _check_container_return_dates(self):
        self.mapped("container_ids")._check_return_date()

class Container(models.Model):
    _name = "containers.container"
    _description = "Container"
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
    eir_file = fields.Binary(string="Comprobante EIR", attachment=True)
    eir_filename = fields.Char(string="Nombre del archivo EIR")
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
    
    def _get_demurrage_values(self, cutoff_date=None):
        self.ensure_one()

        bl = self.bill_of_lading_id
        discharge_date = self.discharge_date

        if not discharge_date or not bl.customer_id or not bl.shipping_line_id:
            raise ValidationError(
                "Completa cliente, naviera y fecha de descarga para calcular."
            )

        cutoff_date = (
            fields.Date.to_date(cutoff_date)
            if cutoff_date
            else fields.Date.context_today(self)
        )
        end_date = self.return_date or cutoff_date

        if end_date < discharge_date:
            raise ValidationError(
                "La fecha de corte o devolución es anterior a la descarga."
            )

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

        condition = self.env["containers.customer.condition"].search(
            [
                ("customer_id", "=", bl.customer_id.id),
                ("shipping_line_id", "=", bl.shipping_line_id.id),
            ],
            limit=1,
        )

        extra_days = condition.extra_free_days if condition else 0
        days_outside = (end_date - discharge_date).days + 1
        free_days = tariff.free_days + extra_days
        delay_days = max(0, days_outside - free_days)

        usd = self.env.ref("base.USD")
        shipping_amount = usd.round(
            tariff._calculate_demurrage(delay_days)
        )

        percentage = bl.customer_id.administration_percentage
        customer_amount = usd.round(
            shipping_amount * (1 + percentage / 100)
        )

        return {
            "days_outside": days_outside,
            "free_days": free_days,
            "delay_days": delay_days,
            "shipping_amount_usd": shipping_amount,
            "customer_amount_usd": customer_amount,
            "is_estimate": not bool(self.return_date),
        }

    @api.depends(
        "discharge_date",
        "return_date",
        "container_type",
        "bill_of_lading_id.customer_id",
        "bill_of_lading_id.shipping_line_id",
        "bill_of_lading_id.customer_id.administration_percentage",
    )
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

            if not re.fullmatch(r"[A-Z]{3}[UJZ][0-9]{7}", number):
                raise ValidationError(
                    "Escribe el número de contenedor en mayúsculas y sin espacios. "
                    "Debe tener 4 letras (la cuarta U, J o Z) y 7 dígitos."
                )

            total = 0
            for position, character in enumerate(number[:10]):
                value = (
                    int(character)
                    if character.isdigit()
                    else ISO_LETTER_VALUES[character]
                )
                total += value * (2 ** position)

            expected_digit = (total % 11) % 10
            if int(number[-1]) != expected_digit:
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