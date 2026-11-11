from odoo import Command
from odoo.tests import TransactionCase


class TestDemurrage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        (
            cls.atlantico,
            cls.mar_del_sur,
            cls.importadora,
            cls.ferreteria,
            cls.textiles,
            cls.frutas,
        ) = cls.env["res.partner"].create([
            {"name": "Prueba - Naviera Atlántico"},
            {"name": "Prueba - Mar del Sur Line"},
            {"name": "Prueba - Importadora Sol"},
            {"name": "Prueba - Ferretería El Tornillo"},
            {
                "name": "Prueba - Textiles Andinos",
                "administration_percentage": 5,
            },
            {"name": "Prueba - Frutas del Valle"},
        ])

        cls.env["containers.customer.condition"].create([
            {
                "customer_id": cls.ferreteria.id,
                "shipping_line_id": cls.atlantico.id,
                "extra_free_days": 5,
            },
            {
                "customer_id": cls.textiles.id,
                "shipping_line_id": cls.mar_del_sur.id,
                "extra_free_days": 3,
            },
        ])

        cls._create_tariff(
            cls.atlantico, "40HC", "2026-01-01", False, 7,
            [(1, 5, 60), (6, 10, 120), (11, 0, 180)],
        )
        cls._create_tariff(
            cls.atlantico, "20DV", "2026-01-01", False, 7,
            [(1, 5, 35), (6, 10, 70), (11, 0, 110)],
        )
        cls._create_tariff(
            cls.atlantico, "40RF", "2026-01-01", False, 4,
            [(1, 5, 150), (6, 0, 250)],
        )
        cls._create_tariff(
            cls.mar_del_sur, "40DV", "2026-01-01", "2026-06-30", 10,
            [(1, 7, 75), (8, 0, 150)],
        )
        cls._create_tariff(
            cls.mar_del_sur, "40DV", "2026-07-01", False, 8,
            [(1, 7, 85), (8, 0, 170)],
        )
        cls._create_tariff(
            cls.mar_del_sur, "20DV", "2026-07-01", False, 8,
            [(1, 7, 45), (8, 0, 95)],
        )

    @classmethod
    def _create_tariff(
        cls, shipping_line, container_type, valid_from, valid_to,
        free_days, tiers,
    ):
        cls.env["containers.tariff"].create({
            "name": f"{shipping_line.name} {container_type} {valid_from}",
            "shipping_line_id": shipping_line.id,
            "container_type": container_type,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "free_days": free_days,
            "tier_ids": [
                Command.create({
                    "day_from": first_day,
                    "day_to": last_day,
                    "daily_rate": rate,
                })
                for first_day, last_day, rate in tiers
            ],
        })

    def _create_container(
        self, number, customer, shipping_line, container_type,
        discharge_date, return_date,
    ):
        bl = self.env["containers.bill.of.lading"].create({
            "name": f"PRUEBA-{number}",
            "customer_id": customer.id,
            "shipping_line_id": shipping_line.id,
            "discharge_date": discharge_date,
        })
        return self.env["containers.container"].create({
            "name": number,
            "bill_of_lading_id": bl.id,
            "container_type": container_type,
            "return_date": return_date,
        })

    def test_demurrage_cases_1_to_8(self):
        # Cada resultado contiene días afuera, libres, de demora,
        # cobro de naviera, cobro al cliente y si es estimado.
        cases = [
            (
                "TSTU9000015", self.importadora, self.atlantico, "40HC",
                "2026-03-02", "2026-03-20", (19, 7, 12, 1260, 1386, False),
            ),
            (
                "TSTU9000020", self.ferreteria, self.atlantico, "20DV",
                "2026-04-10", "2026-04-21", (12, 12, 0, 0, 0, False),
            ),
            (
                "TSTU9000036", self.textiles, self.mar_del_sur, "40DV",
                "2026-06-28", "2026-07-15", (18, 13, 5, 375, 393.75, False),
            ),
            (
                "TSTU9000041", self.frutas, self.atlantico, "40RF",
                "2026-08-01", "2026-08-14", (14, 4, 10, 2000, 2200, False),
            ),
            (
                "TSTU9000057", self.importadora, self.mar_del_sur, "20DV",
                "2026-09-05", False, (16, 8, 8, 410, 451, True),
            ),
            (
                "TSTU9000062", self.importadora, self.atlantico, "20DV",
                "2026-05-04", "2026-05-10", (7, 7, 0, 0, 0, False),
            ),
            (
                "TSTU9000078", self.importadora, self.atlantico, "20DV",
                "2026-05-04", "2026-05-11", (8, 7, 1, 35, 38.50, False),
            ),
            (
                "TSTU9000083", self.importadora, self.atlantico, "20DV",
                "2026-09-14", "2026-09-14", (1, 7, 0, 0, 0, False),
            ),
        ]

        for case_number, case in enumerate(cases, start=1):
            with self.subTest(case=case_number):
                *container_data, expected = case
                container = self._create_container(*container_data)

                if case_number == 5:
                    container = container.with_context(
                        demurrage_cutoff_date="2026-09-20",
                    )

                self.assertTrue(
                    container.calculation_ok, container.calculation_message,
                )
                self.assertEqual(
                    (
                        container.days_outside,
                        container.free_days,
                        container.delay_days,
                        container.shipping_amount_usd,
                        container.customer_amount_usd,
                        container.is_estimate,
                    ),
                    expected,
                )

    def test_case_9_missing_tariff(self):
        container = self._create_container(
            "TSTU9000099", self.frutas, self.mar_del_sur, "40RF",
            "2026-08-03", "2026-08-20",
        )

        self.assertFalse(container.calculation_ok)
        self.assertIn("Falta una tarifa", container.calculation_message)