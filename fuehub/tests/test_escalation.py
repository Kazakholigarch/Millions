from app.ai.escalation import needs_clinical_escalation


def test_flags_medical_history_question():
    assert needs_clinical_escalation("Can you review my medical history first?")


def test_flags_medication_interaction_question():
    assert needs_clinical_escalation("I'm on a blood thinner, is that a problem?")


def test_flags_candidacy_question():
    assert needs_clinical_escalation("Am I a good candidate for this?")


def test_flags_german_health_condition():
    assert needs_clinical_escalation("Ich habe Diabetes, ist das ein Problem für die Operation?")


def test_flags_arabic_pregnancy_question():
    assert needs_clinical_escalation("هل يمكنني إجراء العملية وأنا حامل؟")


def test_does_not_flag_cost_question():
    assert needs_clinical_escalation("How much does it cost for 3000 grafts?") == []


def test_does_not_flag_technique_question():
    assert needs_clinical_escalation("What's the difference between FUE and DHI?") == []


def test_does_not_flag_package_question():
    assert needs_clinical_escalation("Does the package include a hotel and transfers?") == []
