"""Analyze the synthetic scenario with Gemini, saving its explicitly labeled packet."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backend import config,pipeline

async def main():
    ctx=json.loads((config.DATA/'gemini_scenario_sd1024.json').read_text())['context']
    packet=await pipeline.analyze((config.DATA/'viral.png').read_bytes(),'image/png',config.scenario()['claim'],ctx,live=True)
    folder=config.CACHE/'gemini';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(packet['image_hash']+'.json');path.write_text(json.dumps(packet,ensure_ascii=False,indent=2));path.chmod(0o600)
    print('Saved Gemini exercise evidence:',path)
if __name__=='__main__':asyncio.run(main())
