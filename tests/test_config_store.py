from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from config_store import SettingsStore


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=SettingsStore(Path(self.temp.name)/'settings.sqlite3')
    def tearDown(self):
        self.temp.cleanup()
    def test_guilds_do_not_inherit_private_configuration(self):
        self.store.set_many({'twitch.channel_id':'123','twitch.channels':['example']},guild_id=1)
        self.assertIsNone(self.store.get('twitch.channel_id',2))
        self.assertEqual(self.store.get('twitch.channels',2),[])
    def test_invalid_batch_is_atomic(self):
        with self.assertRaises(ValueError):
            self.store.set_many({'twitch.channel_id':'123','twitch.channels':['bad login']},guild_id=1)
        self.assertIsNone(self.store.get('twitch.channel_id',1))
    def test_explicit_scope_is_required(self):
        with self.assertRaises(ValueError):self.store.get('twitch.channels')
        with self.assertRaises(ValueError):self.store.set_many({'presence.text':'test'},guild_id=1)
    def test_concurrent_list_changes_preserve_entries(self):
        def add(name):self.store.update_names('twitch.channels',name,True,1)
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(add,['alice','bob','carol']))
        self.assertEqual(set(self.store.get('twitch.channels',1)),{'alice','bob','carol'})

if __name__=='__main__':unittest.main()
