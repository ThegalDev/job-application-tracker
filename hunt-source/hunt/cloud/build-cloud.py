"""Build the owner-private review console without copying runtime career data."""
import json
import shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WEB=ROOT.parent/'web'
assets={path:(WEB/name).read_text() for path,name in [('/','index.html'),('/app.js','app.js'),('/style.css','style.css')]}
# The hosted dashboard has an explicit deployment-specific footer label.
assets['/']=assets['/'].replace('● Private · on this computer','● Private · phone review console')
profile=json.loads((ROOT.parent/'writing-profile.json').read_text())
instructions=(ROOT.parent/'drafting-instructions.txt').read_text()
source='const DRAFTING_INSTRUCTIONS='+json.dumps(instructions,ensure_ascii=False)+';\n'+'const WRITING_PROFILE='+json.dumps(profile,ensure_ascii=False)+';\n'+'const ASSETS='+json.dumps(assets,ensure_ascii=False)+';\n'+(ROOT/'server.mjs').read_text()
out=ROOT/'dist/server/index.js';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(source)
manifest=ROOT/'.openai/hosting.json'
config=json.loads(manifest.read_text());config['r2']='BUCKET';config['d1']=None;config.pop('static',None)
manifest.write_text(json.dumps(config,indent=2)+'\n')
runtime=ROOT/'agent-runtime';runtime.mkdir(exist_ok=True)
for path in ROOT.parent.glob('*.py'):
    if not path.name.startswith('test_'):shutil.copy2(path,runtime/path.name)
for name in ('writing-profile.json','drafting-instructions.txt'):shutil.copy2(ROOT.parent/name,runtime/name)
print('Built private Worker console and reviewed agent runtime source; no career snapshots or credentials in build.')
