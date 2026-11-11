from odoo import fields, models
from odoo.exceptions import ValidationError


class ContainerTariff(models.Model):
    _name = "containers.tariff"
    _description = "Container Tariff"

    _sql_constraints = [
        (
            "free_days_nonnegative",
            "CHECK(free_days >= 0)",
            "Los días libres no pueden ser negativos.",
        ),
        (
            "valid_date_order",
            "CHECK(valid_to IS NULL OR valid_to >= valid_from)",
            "La fecha final de vigencia debe ser igual o posterior a la inicial.",
        ),
        (
            "no_overlapping_validity",
            """
            EXCLUDE USING gist (
                shipping_line_id WITH =,
                container_type WITH =,
                daterange(valid_from, valid_to, '[]') WITH &&
            )
            WHERE (
                valid_from IS NOT NULL
                AND (valid_to IS NULL OR valid_to >= valid_from)
            )
            """,
            "Ya existe una tarifa para esta naviera y tipo en esa vigencia.",
        ),
    ]

    name = fields.Char(
        string="Nombre de la tarifa",
        required=True,
    )

    shipping_line_id = fields.Many2one(
        "res.partner",
        string="Naviera",
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

    valid_from = fields.Date(
        string="Vigente desde",
        required=True,
    )

    valid_to = fields.Date(
        string="Vigente hasta",
    )

    free_days = fields.Integer(
        string="Días libres",
        required=True,
    )

    tier_ids = fields.One2many(
        "containers.tariff.tier",
        "tariff_id",
        string="Tramos",
    )

    def _validate_tier_coverage(self):
        for tariff in self:
            tiers = tariff.tier_ids.sorted("day_from")

            if not tiers:
                raise ValidationError(
                    "La tarifa debe tener al menos un tramo."
                )

            if tiers[-1].day_to != 0:
                raise ValidationError(
                    "El último tramo debe tener día final 0 "
                    "para cubrir la demora sin límite."
                )

            next_day = 1

            for tier in tiers:
                if tier.day_from != next_day:
                    raise ValidationError(
                        f"El siguiente tramo debe comenzar "
                        f"en el día {next_day}."
                    )

                if tier.day_to == 0 and tier != tiers[-1]:
                    raise ValidationError(
                        "Solo el último tramo puede quedar sin límite."
                    )

                next_day = tier.day_to + 1
    def _calculate_demurrage(self, delay_days):
        self.ensure_one()
        self._validate_tier_coverage()

        if delay_days < 0:
            raise ValidationError(
                "Los días de demora no pueden ser negativos."
            )

        total = 0.0

        for tier in self.tier_ids.sorted("day_from"):
            last_day = (
                min(delay_days, tier.day_to)
                if tier.day_to
                else delay_days
            )

            days_in_tier = max(0, last_day - tier.day_from + 1)
            total += days_in_tier * tier.daily_rate

        return total
    
    def action_check_tiers(self):
        self._validate_tier_coverage()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Tramos correctos",
                "message": "La tarifa cubre todos los días de demora.",
                "type": "success",
                "sticky": False,
            },
        }


class ContainerTariffTier(models.Model):
    _name = "containers.tariff.tier"
    _description = "Container Tariff Tier"
    _order = "day_from, id"
    _rec_name = "day_from"

    _sql_constraints = [
        (
            "valid_day_range",
            """
            CHECK(
                day_from >= 1
                AND day_to >= 0
                AND (day_to = 0 OR day_to >= day_from)
            )
            """,
            "El tramo debe comenzar desde el día 1 o posterior. "
            "El día final debe ser igual o mayor al inicial, "
            "o 0 para indicar sin límite.",
        ),
        (
            "positive_daily_rate",
            "CHECK(daily_rate > 0)",
            "La tarifa diaria debe ser mayor que cero.",
        ),
        (
            "no_overlapping_tiers",
            """
            EXCLUDE USING gist (
                tariff_id WITH =,
                int8range(
                    day_from::bigint,
                    NULLIF(day_to, 0)::bigint,
                    '[]'
                ) WITH &&
            )
            WHERE (
                day_from >= 1
                AND day_to >= 0
                AND (day_to = 0 OR day_to >= day_from)
            )
            """,
            "Los días de este tramo se cruzan con otro tramo de la tarifa.",
        ),
    ]

    tariff_id = fields.Many2one(
        "containers.tariff",
        string="Tarifa",
        required=True,
        ondelete="cascade",
    )

    day_from = fields.Integer(
        string="Desde el día de demora",
        required=True,
    )

    day_to = fields.Integer(
        string="Hasta el día de demora",
        help="Usa 0 para indicar que el tramo no tiene límite.",
    )

    daily_rate = fields.Float(
        string="Tarifa diaria (USD)",
        digits=(16, 2),
        required=True,
    )