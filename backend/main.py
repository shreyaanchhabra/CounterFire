"""Local Firebreak desk. Expose only the separate callback service publicly."""
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend.config import ROOT
from backend.society_service import Conflict, EpisodeManager


def create_app(manager=None):
    app=FastAPI(title='Firebreak fictional society',docs_url=None,redoc_url=None,openapi_url=None)
    controller=manager or EpisodeManager()
    app.state.controller=controller

    @app.exception_handler(Conflict)
    async def conflict(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':str(exc)},status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':str(exc)},status_code=422)

    @app.exception_handler(KeyError)
    async def missing(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Unknown episode, branch, or recording'},status_code=404)

    @app.middleware('http')
    async def local_origin(request,call_next):
        origin=request.headers.get('origin')
        if request.method=='POST' and origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail':'Use the local desk to change episode state'},status_code=403)
        return await call_next(request)

    @app.get('/')
    def index():return FileResponse(ROOT/'frontend/index.html')
    @app.get('/baseline')
    def baseline():return FileResponse(ROOT/'firebreak-ui.html')
    app.mount('/static',StaticFiles(directory=ROOT/'frontend'),name='static')
    @app.get('/api/health')
    def health():return controller.health()
    @app.get('/api/scenario')
    def scenario():return {'scenario':controller.scenario,'groups':[{'id':i,'name':n} for i,n in enumerate(__import__('backend.schemas',fromlist=['GROUPS']).GROUPS)]}
    @app.get('/api/recordings')
    def recordings():return controller.recordings()
    @app.post('/api/episodes')
    async def create(request:Request):
        body=await request.json()
        if not isinstance(body,dict):raise ValueError('Expected a JSON object')
        return controller.create(body.get('mode','fixture'),body.get('recording_id'))
    @app.get('/api/episodes/{identifier}')
    def view(identifier:str):return controller.view(identifier)
    @app.get('/api/episodes/{identifier}/events')
    async def events(identifier:str,request:Request):
        controller.view(identifier)
        async def stream():
            version=-1
            while not await request.is_disconnected():
                view=controller.view(identifier)
                if view['version']!=version:
                    version=view['version'];yield 'event: snapshot\ndata: '+json.dumps(view,ensure_ascii=False)+'\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})
    @app.post('/api/episodes/{identifier}/{operation:path}')
    async def mutate(identifier:str,operation:str,request:Request):
        body=await request.json()
        if not isinstance(body,dict):raise ValueError('Expected a JSON object')
        if operation=='advance':return controller.advance(identifier)
        if operation=='evidence':return controller.evidence(identifier,body)
        if operation=='drafts':return controller.drafts(identifier)
        if operation=='intervention':return controller.propose(identifier,body)
        if operation=='approve':return controller.approve(identifier,body.get('revision'),body.get('content_hash'))
        if operation=='branch':return controller.branch(identifier,body.get('kind'),body.get('name'),body.get('intervention'))
        if operation=='select-branch':return controller.select(identifier,body.get('branch_id'))
        if operation=='record':return controller.record(identifier)
        if operation=='replies':return controller.replies(identifier,body.get('questions'))
        raise HTTPException(404,'Unknown operation')
    return app


def app_factory():return create_app()
