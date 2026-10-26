from django.urls import path
from . import views

urlpatterns = [
    
    path("", views.index, name="index"),
        path(
        "login/",
        views.GemsLoginView.as_view(),
        name="login",
    ),


    path("assets/", views.assets, name="assets"),
    path(
        "asset-details/<str:asset_tag>/",
        views.asset_details,
        name="asset-details",
    ),
    path(
        "assets/<str:asset_tag>/assign/",
        views.asset_assign,
        name="asset-assign",
    ),
    path("assets/create/", views.asset_create, name="asset-create"),
    path("assets/<str:asset_tag>/edit/", views.asset_update, name="asset-update"),
    path(
        "assets/<str:asset_tag>/transfer/",
        views.asset_transfer,
        name="asset-transfer",
    ),
    path(
        "assets/<str:asset_tag>/edit/",
        views.asset_update,
        name="asset-update",
    ),
    path(
        "assets/<str:asset_tag>/return/",
        views.asset_return,
        name="asset-return",
    ),
    path(
        "assets/<str:asset_tag>/repair/",
        views.asset_repair,
        name="asset-repair",
    ),
    path(
        "quality-inspection/",
        views.quality_inspection,
        name="quality-inspection",
    ),
    path(
    "quality-inspection/<int:inspection_id>/",
        views.quality_inspection_detail,
    name="quality-inspection-detail",
    ),
    path(
    "quality-inspections/",
    views.quality_inspections,
    name="quality-inspections",
    ),
    path("consumables/", views.consumables, name="consumables"),
    path(
        "consumables/<int:item_id>/move/",
        views.consumable_stock_move,
        name="consumable-stock-move",
    ),
    path(
        "consumables/<int:item_id>/",
        views.consumable_detail,
        name="consumable-detail",
    ),

    

    path("employees/", views.employees, name="employees"),
    path("employee-details/", views.employee_details, name="employee-details"),
    path("reports/", views.reports, name="reports"),
    path("audit-logs/", views.audit_logs, name="audit-logs"),
    path("settings/", views.settings, name="settings"),
]
