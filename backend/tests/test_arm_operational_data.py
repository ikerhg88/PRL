from __future__ import annotations

from app.db.models import DocumentType
from app.services.arm_operational_data import _norm, _worker_document_type


def test_arm_worker_document_type_splits_training_variants() -> None:
    codes = [
        "CAE.WORKER.PPE_DELIVERY",
        "CAE.WORKER.PRL_50H_COURSE",
        "CAE.WORKER.FORKLIFT_TRAINING",
        "CAE.WORKER.MEWP_TRAINING",
        "CAE.WORKER.OVERHEAD_CRANE_TRAINING",
        "CAE.WORKER.HEIGHT_WORKS_TRAINING",
        "CAE.WORKER.METAL_RECYCLING",
        "CAE.WORKER.METAL_TRAINING",
        "CAE.WORKER.PRL_ART19",
        "CAE.WORKER.BASIC_PRL_COURSE",
        "ARM.WORKER.TRAINING_EVIDENCE",
    ]
    type_by_code = {
        code: DocumentType(code=code, name=code, entity_scope="worker", requires_expiration=False)
        for code in codes
    }

    examples = {
        "Diploma_CARLOS_carretilla.pdf": "CAE.WORKER.FORKLIFT_TRAINING",
        "Diploma_PLATAFORMA_Carlos.pdf": "CAE.WORKER.MEWP_TRAINING",
        "Diploma_ALTURAS_CARLOS.pdf": "CAE.WORKER.HEIGHT_WORKS_TRAINING",
        "curso_metal_y_reciclaje_03-2023.pdf": "CAE.WORKER.METAL_RECYCLING",
        "Carlos_metal_4_horas_28-03-2023.pdf": "CAE.WORKER.METAL_TRAINING",
        "6_-_ART.19_Fernando_-_22-07-2025.pdf": "CAE.WORKER.PRL_ART19",
        "6_-_PRL_Art.19_Daniel.pdf": "CAE.WORKER.PRL_ART19",
        "curso_prevencio_n_50_h_iva_n.pdf": "CAE.WORKER.PRL_50H_COURSE",
        "entrega_EPIs_Alicia.pdf": "CAE.WORKER.PPE_DELIVERY",
    }

    for filename, expected_code in examples.items():
        assert _worker_document_type(_norm(filename), type_by_code).code == expected_code
