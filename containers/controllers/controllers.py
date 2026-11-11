# -*- coding: utf-8 -*-
# from odoo import http


# class Containers(http.Controller):
#     @http.route('/containers/containers', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/containers/containers/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('containers.listing', {
#             'root': '/containers/containers',
#             'objects': http.request.env['containers.containers'].search([]),
#         })

#     @http.route('/containers/containers/objects/<model("containers.containers"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('containers.object', {
#             'object': obj
#         })

