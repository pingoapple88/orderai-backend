import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Plan


def test_same_plan_name_can_exist_for_different_sales_channels(db_session):
    db_session.add_all([
        Plan(name="lite", channel="direct", monthly_price=39000),
        Plan(name="lite", channel="dealer", monthly_price=49000),
        Plan(name="lite", channel="enterprise", monthly_price=0),
    ])
    db_session.commit()

    channels = {
        row.channel for row in db_session.query(Plan).filter(Plan.name == "lite").all()
    }
    assert channels == {"direct", "dealer", "enterprise"}


def test_same_plan_name_and_channel_remains_unique(db_session):
    db_session.add(Plan(name="pro", channel="direct", monthly_price=79000))
    db_session.commit()
    db_session.add(Plan(name="pro", channel="direct", monthly_price=79000))

    with pytest.raises(IntegrityError):
        db_session.commit()
