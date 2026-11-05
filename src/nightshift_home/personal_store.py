"""Small local documents with private atomic writes and reversible task removal."""
from pathlib import Path
import copy
import json
import os
import tempfile
import time
import uuid
from data import HOME

ROOT=HOME/'.config/nightshift-home'


def private_write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.stem+'-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


class NotesStore:
    def __init__(self,path=None):
        self.path=Path(path) if path else ROOT/'notes.json'
        self.text='';self.error='';self.loaded=True
        try:
            value=json.loads(self.path.read_text())
            if not isinstance(value.get('text'),str):raise ValueError()
            self.text=value['text']
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError,AttributeError):
            self.loaded=False;self.error='Saved notes could not be read. The original file has been preserved.'

    def save(self,text):
        if not self.loaded:raise OSError(self.error)
        private_write(self.path,{'text':text,'updated_at':time.time()});self.text=text


class TodoStore:
    def __init__(self,path=None):
        self.path=Path(path) if path else ROOT/'todos.json'
        self.items=[];self.undo_items=[];self.error='';self.loaded=True
        try:
            value=json.loads(self.path.read_text())
            self.items=self.validate(value['items']);self.undo_items=self.validate(value.get('undo_items',[]))
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError,KeyError,AttributeError):
            self.items=[];self.undo_items=[];self.loaded=False;self.error='Saved tasks could not be read. The original file has been preserved.'

    @staticmethod
    def validate(items):
        if not isinstance(items,list):raise ValueError()
        ids=set()
        for item in items:
            if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not isinstance(item.get('text'),str) or not isinstance(item.get('done'),bool):raise ValueError()
            if item['id'] in ids:raise ValueError()
            ids.add(item['id'])
        return items

    def commit(self,items,undo=None):
        if not self.loaded:raise OSError(self.error)
        undo=self.undo_items if undo is None else undo
        private_write(self.path,{'items':items,'undo_items':undo,'updated_at':time.time()})
        self.items=items;self.undo_items=undo

    def add(self,text):
        text=text.strip()
        if not text:return None
        if len(self.items)>=200:raise ValueError('This list has 200 tasks. Remove completed tasks before adding more.')
        if len(text)>500:raise ValueError('Keep each task under 500 characters.')
        item={'id':uuid.uuid4().hex,'text':text,'done':False,'created_at':time.time()}
        self.commit(self.items+[item]);return item['id']

    def update(self,identifier,**changes):
        items=copy.deepcopy(self.items)
        item=next((i for i in items if i['id']==identifier),None)
        if item is None:return
        if 'text' in changes:
            text=changes['text'].strip()
            if not text or len(text)>500:raise ValueError('Enter a task between 1 and 500 characters.')
            item['text']=text
        if 'done' in changes:item['done']=bool(changes['done'])
        self.commit(items)

    def remove(self,identifier):
        removed=[i for i in self.items if i['id']==identifier]
        if removed:self.commit([i for i in self.items if i['id']!=identifier],removed)

    def clear_done(self):
        removed=[i for i in self.items if i['done']]
        if removed:self.commit([i for i in self.items if not i['done']],removed)

    def undo(self):
        ids={i['id'] for i in self.items}
        self.commit(self.items+[i for i in self.undo_items if i['id'] not in ids],[])
