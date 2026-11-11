# -*- coding: utf-8 -*-
{
    'name': "containers",

    'summary': "This module is used for knowing when we have to emp",

    'description': """
Long description of module's purpose
    """,

    'author': "Puerto alto",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Logistic',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base'],

    # always loaded
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/bl_form.xml',
        "views/container_correction_view.xml",
        'views/tariff_view.xml',
        'views/customer_condition_view.xml',
      #  'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}

