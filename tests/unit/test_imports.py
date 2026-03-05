"""
Import tests: verify that all modules can be imported without error.
Covers class definitions, constants, and function signatures
without requiring a database or external service connection.
"""

import importlib


def test_import_models():
    importlib.import_module("src.app.models")


def test_import_schemas():
    for mod in [
        "src.app.schemas.budget",
        "src.app.schemas.common",
        "src.app.schemas.document",
        "src.app.schemas.guide",
        "src.app.schemas.mobility",
        "src.app.schemas.task",
        "src.app.schemas.user",
    ]:
        importlib.import_module(mod)


def test_import_services():
    for mod in [
        "src.app.services.admin_service",
        "src.app.services.auth_service",
        "src.app.services.budget_service",
        "src.app.services.cache_service",
        "src.app.services.checklist_service",
        "src.app.services.document_service",
        "src.app.services.guide_service",
        "src.app.services.mobility_service",
        "src.app.services.notification_service",
        "src.app.services.storage_service",
        "src.app.services.timeline_service",
        "src.app.services.user_service",
    ]:
        importlib.import_module(mod)


def test_import_ai():
    for mod in [
        "src.app.services.ai.ai_service",
        "src.app.services.ai.cache",
        "src.app.services.ai.client",
        "src.app.services.ai.prompts.base",
        "src.app.services.ai.prompts.budget",
        "src.app.services.ai.prompts.checklist",
        "src.app.services.ai.prompts.day_zero",
        "src.app.services.ai.prompts.guide",
        "src.app.services.ai.prompts.timeline",
    ]:
        importlib.import_module(mod)


def test_import_workers():
    for mod in [
        "src.app.workers.ai_prefetch_worker",
        "src.app.workers.notification_worker",
    ]:
        importlib.import_module(mod)


def test_import_db():
    for mod in [
        "src.app.db.base",
        "src.app.db.session",
    ]:
        importlib.import_module(mod)
