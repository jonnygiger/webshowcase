import unittest
from datetime import datetime, timezone
from app import db
from models import User, Group
from tests.test_base import AppTestCase

class TestGroupModel(AppTestCase):

    def test_group_repr(self):
        with self.app.app_context():
            creator = self._create_db_user(username="group_creator_repr")
            group = Group(name="Represent Group", creator_id=creator.id)
            db.session.add(group)
            db.session.commit()
            self.assertEqual(repr(group), "<Group 'Represent Group'>")

    def test_add_member_to_group(self):
        with self.app.app_context():
            creator = self._create_db_user(username="group_creator_add")
            member = self._create_db_user(username="group_member_add")
            group = self._create_db_group(creator_id=creator.id, name="Group For Adding Members")

            group.members.append(member)
            db.session.commit()

            # Re-fetch group and member to ensure session state is current
            group = db.session.get(Group, group.id)
            member = db.session.get(User, member.id)

            self.assertIn(member, group.members)
            self.assertIn(group, member.joined_groups)

    def test_remove_member_from_group(self):
        with self.app.app_context():
            creator = self._create_db_user(username="group_creator_remove")
            member = self._create_db_user(username="group_member_remove")
            group = self._create_db_group(creator_id=creator.id, name="Group For Removing Members")

            group.members.append(member)
            db.session.commit()

            # Re-fetch to ensure relationship is loaded
            group = db.session.get(Group, group.id)
            self.assertIn(member, group.members)

            group.members.remove(member)
            db.session.commit()

            # Re-fetch group and member
            group = db.session.get(Group, group.id)
            member = db.session.get(User, member.id)

            self.assertNotIn(member, group.members)
            self.assertNotIn(group, member.joined_groups)

    def test_group_to_dict(self):
        with self.app.app_context():
            creator = self._create_db_user(username="group_creator_dict")
            group_description = "A test description for dict."
            created_time = datetime.now(timezone.utc) # Approximate, exact match difficult

            group = Group(
                name="Dict Group",
                creator_id=creator.id,
                description=group_description,
                created_at=created_time
            )
            db.session.add(group)
            db.session.commit()

            # Re-fetch to ensure all attributes are loaded correctly, especially defaults or server-side changes
            group_fetched = db.session.get(Group, group.id)

            expected_dict = {
                "id": group_fetched.id,
                "name": "Dict Group",
                "description": group_description,
                "creator_id": creator.id,
                "created_at": group_fetched.created_at.isoformat(), # Use the actual DB value
                "creator_username": creator.username,
            }
            self.assertDictEqual(group_fetched.to_dict(), expected_dict)

    def test_group_creator_relationship(self):
        with self.app.app_context():
            creator = self._create_db_user(username="group_rel_creator")
            group = self._create_db_group(creator_id=creator.id, name="Creator Test Group")

            # Re-fetch group
            group_fetched = db.session.get(Group, group.id)
            self.assertIsNotNone(group_fetched.creator)
            self.assertEqual(group_fetched.creator.id, creator.id)
            self.assertEqual(group_fetched.creator.username, "group_rel_creator")

            # Check back-population
            creator_fetched = db.session.get(User, creator.id)
            self.assertIn(group_fetched, creator_fetched.created_groups)

if __name__ == "__main__":
    unittest.main()
