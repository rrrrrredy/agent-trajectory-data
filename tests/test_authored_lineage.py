import copy,hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import runtime_batch as b,repair_batch as repair,repair_probe_env as env,repair_probe_tasks as tasks,repair_executor as executor,source_catalog as catalog

class AuthoredLineageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent/'_tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'batch';self.repo=Path(self.temp.name)/'repo'
        self.config=b.read(ROOT/'configs/runtime-v0.15/batch.json');self.item=copy.deepcopy(self.config['sources'][0]);self.material=b.read(ROOT/self.item['path'])
        parent_config=b.read(ROOT/'configs/runtime-v0.14/batch.json');parent_material=b.read(ROOT/parent_config['sources'][0]['path'])
        scenario=repair.authored_scenario(parent_config,parent_material,'clean')
        self.parent={k:scenario[k] for k in ('task_id','family_id','source_group_id','split','rights','source_sha256','parent_task_id')}
        self.index=(json.dumps(self.parent,sort_keys=True)+'\n').encode();self.manifest=json.dumps({'files':{'tasks.jsonl':b.sha(self.index)}}).encode()
        archive=self.repo/'artifacts'/self.item['parent']['archive'];archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive,'w') as z:z.writestr('batch/tasks.jsonl',self.index);z.writestr('batch/manifest.json',self.manifest)
        self.item['parent'].update(archive_sha256=b.sha(archive.read_bytes()),index_sha256=b.sha(self.index),manifest_sha256=b.sha(self.manifest))
        repair.freeze_authored_parent(self.repo,self.root,self.item)
        self.save_material()
    def save_material(self):
        path=self.root/'source'/(self.item['task_id']+'.json');path.write_bytes(b.encoded(self.material));self.item['sha256']=b.sha(path.read_bytes())
    def verify_material(self):return repair.authored_material(self.root,self.config,self.item)
    def test_derived_variant_keeps_family_use_and_zero_new_sources(self):
        m=self.verify_material();s=repair.authored_scenario(self.config,m,'clean')
        self.assertEqual(s['family_id'],self.parent['family_id']);self.assertEqual(s['parent_task_id'],self.parent['task_id'])
        self.assertEqual(s['rights'],self.parent['rights']);self.assertEqual(repair.authored_groups([s]),(1,0))
        projected=[catalog.project('v0.14',self.parent,1),catalog.project('v0.15',s,1)]
        resolved=catalog.resolve(projected)
        self.assertEqual(len({x['lineage_group_id'] for x in resolved}),1);self.assertEqual(catalog.stats(resolved)['new_independent_source_groups'],0)
    def test_changed_family_source_or_parent_rejected(self):
        for key in ('family_id','source_group_id','parent_task_id'):
            original=self.material[key];self.material[key]='unrelated';self.save_material()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'parent_lineage_changed'):self.verify_material()
            self.material[key]=original
    def test_changed_split_or_rights_rejected(self):
        self.material['split']='test';self.save_material()
        with self.assertRaisesRegex(ValueError,'parent_use_changed'):self.verify_material()
        self.material['split']='train';self.material['rights']['training_eligible']=False;self.save_material()
        with self.assertRaisesRegex(ValueError,'parent_use_changed'):self.verify_material()
    def test_claimed_parent_without_source_binding_rejected(self):
        self.item.pop('parent')
        with self.assertRaisesRegex(ValueError,'authored_parent_binding_missing'):self.verify_material()
    def test_rehashed_batch_does_not_hide_changed_parent_index(self):
        index_path,_=repair.parent_paths(self.item);(self.root/index_path).write_bytes((json.dumps(dict(self.parent,split='test'))+'\n').encode())
        b.put(self.root/'manifest.json',{'files':b.hashes(self.root)})
        with self.assertRaisesRegex(ValueError,'parent_snapshot_changed'):self.verify_material()
    def test_parent_manifest_must_bind_its_index(self):
        _,path=repair.parent_paths(self.item);(self.root/path).write_bytes(b.encoded({'files':{'tasks.jsonl':'0'*64}}))
        self.item['parent']['manifest_sha256']=b.sha((self.root/path).read_bytes())
        with self.assertRaisesRegex(ValueError,'parent_index_unbound'):self.verify_material()
    def test_parent_archive_checked_before_freezing(self):
        self.item['parent']['archive_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'parent_archive_changed'):repair.freeze_authored_parent(self.repo,Path(self.temp.name)/'bad',self.item)
    def test_delimiter_substitution_passes_old_cases_but_fails_new_case(self):
        m=self.verify_material();prior=b.read(ROOT/'configs/runtime-v0.14/scoped-event-regression.json')
        for case in prior['public_cases']+prior['private_cases']+[m['reference_probe']]:
            self.assertTrue(env.equal(executor.execute(m['partial'],case['input']),case['expected']))
        new=m['private_cases'][-1];self.assertFalse(env.equal(executor.execute(m['partial'],new['input']),new['expected']))
        for case in m['public_cases']+m['private_cases']:
            self.assertTrue(env.equal(env.oracle(case['input']),case['expected']))
    def test_reference_passes_and_all_fifteen_controls_fail(self):
        s=repair.authored_scenario(self.config,self.verify_material(),'clean')
        reference=tasks.run_reference(s);self.assertEqual(b.verify_episode(s,reference)['reward'],1)
        controls=repair.authored_controls(s);self.assertEqual(len(controls),15)
        for control in controls:
            with self.subTest(control=control):self.assertEqual(b.verify_episode(s,tasks.run_reference(s,control))['reward'],0)

if __name__=='__main__':unittest.main()