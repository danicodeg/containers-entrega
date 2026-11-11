from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    administration_percentage = fields.Float(
        string="Administración de demoras (%)",
        default=10.0,
    )

    _sql_constraints = [
        (
            "administration_percentage_nonnegative",
            "CHECK(administration_percentage >= 0)",
            "El porcentaje de administración no puede ser negativo.",
        ),
    ]


class CustomerShippingCondition(models.Model):
    _name = "containers.customer.condition"
    _description = "Customer Shipping Condition"

    customer_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        required=True,
        ondelete="restrict",
    )

    shipping_line_id = fields.Many2one(
        "res.partner",
        string="Naviera",
        required=True,
        ondelete="restrict",
    )
    administration_percentage = fields.Float(
        string="Administración del cliente (%)",
        related="customer_id.administration_percentage",
        readonly=False,
        help="Este porcentaje aplica al cliente con todas sus navieras.",
    )

    extra_free_days = fields.Integer(
        string="Días libres extra",
        default=0,
        required=True,
    )

    _sql_constraints = [
        (
            "unique_customer_shipping_line",
            "UNIQUE(customer_id, shipping_line_id)",
            "Ya existe una condición para este cliente y esta naviera.",
        ),
        (
            "extra_free_days_nonnegative",
            "CHECK(extra_free_days >= 0)",
            "Los días libres extra no pueden ser negativos.",
        ),
    ]