"""Gemini evidence chain merged from origin/gemini, used by native episodes.

Prosecutor and Defender run concurrently, then Judge sees both arguments.
Fixture content is explicit; live failures never substitute fixture findings.
"""
import asyncio
import hashlib
import json

from . import config
from .gemini_schemas import DefenderOut, JudgeOut, ProsecutorOut


def fixture(name, schema):
    return schema.model_validate_json((config.FIXTURES/(name+'.json')).read_text())


async def analyze(image: bytes, mime: str, claim: str, ctx: dict, live: bool, progress=None):
    stages={}
    def emit(name,status):
        stages[name]=status
        if progress:progress(dict(stages))
    if live:
        from .agents import prosecutor, defender, judge
        async def prosecution():
            emit('prosecutor','running')
            out=await asyncio.wait_for(prosecutor.run(image,mime,claim,ctx),config.TIMEOUTS['prosecutor'])
            emit('prosecutor','done');return out
        async def defense():
            emit('defender','running')
            out=await asyncio.wait_for(defender.run(claim,context_line(ctx),image,mime),config.TIMEOUTS['defender'])
            emit('defender','done');return out
        tasks=[asyncio.create_task(prosecution()),asyncio.create_task(defense())]
        try:pro,dfn=await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                if not t.done():t.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
        emit('judge','running')
        jdg=await asyncio.wait_for(judge.run(claim,pro,dfn,judge_targets(ctx)),config.TIMEOUTS['judge'])
        emit('judge','done')
    else:
        pro=fixture('prosecutor',ProsecutorOut);dfn=fixture('defender',DefenderOut);jdg=fixture('judge',JudgeOut)
        for stage in ('prosecutor','defender','judge'):emit(stage,'done')
    # Findings are model assessments, not independently established emergency facts.
    facts=['Image assessment: '+f.label for f in pro.findings]
    facts.append('Judge assessment: '+jdg.reasoning)
    return {'verdict':jdg.verdict,'confidence':jdg.confidence,'reasoning':jdg.reasoning,
            'missing':[v.model_dump() for v in jdg.missing],'findings':[f.model_dump() for f in pro.findings],
            'prosecutor':pro.model_dump(),'defender':dfn.model_dump(),'judge':jdg.model_dump(),
            'verified_facts':facts,'source':'gemini' if live else 'fixture',
            'assessment_kind':'model assessment; not independently verified emergency information',
            'image_hash':hashlib.sha256(image).hexdigest(),'source_refs':['supplied-image'],
            'safety_action':'Check official evacuation updates before sharing. This is a fictional exercise.',
            'official_source':'https://www.readysandiego.org/'}


def context_line(ctx):
    return f"Posted {ctx.get('post_time','unknown')} at {ctx.get('location','unknown')}. {ctx.get('known_facts','')}".strip()


def judge_targets(ctx):
    return [v for v in [ctx.get('poster')]+ctx.get('agencies',[]) if v]
