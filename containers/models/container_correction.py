from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

class ContainerCorrection(models.Model):
    _name = "containers.container.correction"
    _description = "Solicitud de corrección de contenedor"
    _order = "id desc"
    _rec_name = "container_id"

    container_id = fields.Many2one(
        "containers.container",
        string="Contenedor",
        required=True,
        ondelete="restrict",
    )
    corrected_return_date = fields.Date(
        string="Fecha de devolución corregida",
        required=True,
    )
    reason = fields.Text(string="Motivo de la solicitud", required=True)
    eir_filename = fields.Char(string="Nombre del archivo EIR")
    eir_file = fields.Binary(string="EIR de la corrección", attachment=True)

    state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("approved", "Aprobada"),
            ("rejected", "Rechazada"),
        ],
        string="Estado",
        default="pending",
        required=True,
        readonly=True,
        copy=False,
    )
    review_note = fields.Text(string="Observación de Facturación", copy=False)
    reviewed_by_id = fields.Many2one(
        "res.users",
        string="Revisado por",
        readonly=True,
        copy=False,
    )
    reviewed_at = fields.Datetime(
        string="Fecha de revisión",
        readonly=True,
        copy=False,
    )
    
    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create([
            {
                **vals,
                "state": "pending",
                "review_note": False,
                "reviewed_by_id": False,
                "reviewed_at": False,
                "adjusted_customer_amount_usd": 0.0,
                "customer_difference_usd": 0.0,
            }
            for vals in vals_list
        ])

        today = fields.Date.context_today(self)
        for request in requests:
            container = request.container_id
            container.check_access_rights("read")
            container.check_access_rule("read")

            if container.state != "invoiced":
                raise ValidationError(
                    "Solo puedes solicitar correcciones para contenedores facturados."
                )

            if not request.reason.strip():
                raise ValidationError("Escribe el motivo de la solicitud.")

            corrected_date = request.corrected_return_date
            if corrected_date < container.discharge_date or corrected_date > today:
                raise ValidationError(
                    "La fecha corregida debe estar entre la descarga efectiva y hoy."
                )

            if corrected_date == container.return_date:
                raise ValidationError(
                    "La fecha corregida debe ser distinta de la fecha registrada."
                )

        return requests
    
    adjusted_customer_amount_usd = fields.Float(
        string="Importe corregido al cliente (USD)",
        digits=(16, 2),
        readonly=True,
        copy=False,
    )
    customer_difference_usd = fields.Float(
        string="Diferencia para el cliente (USD)",
        digits=(16, 2),
        readonly=True,
        copy=False,
    )

    def _check_pending_review(self):
        self.ensure_one()
        self.check_access_rights("read")
        self.check_access_rule("read")

        if not self.env.user.has_group("containers.group_container_billing"):
            raise AccessError("Solo Facturación puede revisar solicitudes.")

        if self.state != "pending":
            raise ValidationError("Esta solicitud ya fue revisada.")

    def action_approve(self):
        self._check_pending_review()
        container = self.container_id
        original_values = container.invoiced_values

        if container.state != "invoiced" or not original_values:
            raise ValidationError("El contenedor debe tener un cálculo facturado.")

        adjusted_values = container._get_demurrage_values(
            corrected_return_date=self.corrected_return_date,
        )
        adjusted_amount = adjusted_values["customer_amount_usd"]
        previous_approval = self.search(
            [
                ("container_id", "=", container.id),
                ("state", "=", "approved"),
            ],
            order="reviewed_at desc, id desc",
            limit=1,
        )
        reference_amount = (
            previous_approval.adjusted_customer_amount_usd
            if previous_approval
            else original_values["customer_amount_usd"]
        )
        usd = self.env.ref("base.USD")

        self.sudo().write({
            "state": "approved",
            "reviewed_by_id": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
            "adjusted_customer_amount_usd": adjusted_amount,
            "customer_difference_usd": usd.round(adjusted_amount - reference_amount),
        })
        return True

    def action_reject(self):
        self._check_pending_review()
        self.sudo().write({
            "state": "rejected",
            "reviewed_by_id": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
        })
        return True