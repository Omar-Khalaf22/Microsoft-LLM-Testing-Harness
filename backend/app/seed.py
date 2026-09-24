from sqlalchemy import select

from app.database import SessionLocal
from app.models import Model, Test, TestVersion

TEST_ID = "json_test_001"
TEST_VERSION = 1
MODEL_ID = "local_model_001"

PROMPT = (
    "Return the following customer information as JSON with exactly the fields "
    '"name" and "age": John is 25 years old.'
)


def seed_prototype_data() -> None:
    with SessionLocal.begin() as session:
        test = session.get(Test, TEST_ID)

        if test is None:
            test = Test(
                id=TEST_ID,
                name="Valid customer JSON",
            )
            session.add(test)

        model = session.get(Model, MODEL_ID)

        if model is None:
            model = Model(
                id=MODEL_ID,
                name="local-model-name",
            )
            session.add(model)

        test_version = session.scalar(
            select(TestVersion).where(
                TestVersion.test_id == TEST_ID,
                TestVersion.version == TEST_VERSION,
            )
        )

        if test_version is None:
            session.add(
                TestVersion(
                    test_id=TEST_ID,
                    version=TEST_VERSION,
                    prompt=PROMPT,
                    evaluation_definition={"method": "valid_json"},
                )
            )

    print("Prototype seed data is ready.")


if __name__ == "__main__":
    seed_prototype_data()
