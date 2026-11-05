"""Validated RGB palettes and deterministic color transforms for desktop themes."""
import colorsys
import json
import re
from data import HOME

STATE=HOME/'.config/nightshift-home/theme.json'
DEFAULT={'primary':'#58d8f2','secondary':'#bb9af7','highlight':'#ff6bb4','darkness':60,'glow':60,'editors':False}
PRESETS={
    'Midnight cyan':DEFAULT,
    'Aurora glass':{**DEFAULT,'primary':'#2b7368','darkness':25,'glow':100},
    'Cyber violet':{**DEFAULT,'primary':'#b58cff','secondary':'#ff78c8','highlight':'#64e6ff'},
    'Aurora mint':{**DEFAULT,'primary':'#65e8bb','secondary':'#61bfff','highlight':'#e6a9ff'},
    'Ember':{**DEFAULT,'primary':'#ffad66','secondary':'#ff718c','highlight':'#ffd782'},
    'Arctic':{**DEFAULT,'primary':'#c9eaff','secondary':'#adc5ff','highlight':'#f0deff','glow':35},
}

def hex_color(value):
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):raise ValueError('Use a six-digit hex color, such as #58D8F2.')
    return value.lower()

def validate(value):
    if not isinstance(value,dict):raise ValueError('Invalid palette')
    result={**DEFAULT,**{k:v for k,v in value.items() if k in DEFAULT}}
    for key in ('primary','secondary','highlight'):result[key]=hex_color(result[key])
    for key in ('darkness','glow'):
        if type(result[key]) is not int or not 0<=result[key]<=100:raise ValueError(key.title()+' must be between 0 and 100.')
    if type(result['editors']) is not bool:raise ValueError('Editor matching must be on or off.')
    return result

def load_state(path=STATE):
    try:
        value=json.loads(path.read_text());value['palette']=validate(value['palette'])
        if value.get('theme_name') not in ('Midnight-Cyan','Nightshift-RGB-A','Nightshift-RGB-B'):raise ValueError('Invalid theme name')
        return value
    except (OSError,ValueError,TypeError,KeyError):return {'palette':DEFAULT.copy(),'theme_name':'Midnight-Cyan','applied_at':None}

def rgb(value):return tuple(int(value[i:i+2],16)/255 for i in (1,3,5))
def hex_rgb(value):return '#'+''.join(f'{max(0,min(255,round(v*255))):02x}' for v in value)
def luminance(value):
    channels=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb(value)]
    return sum(v*w for v,w in zip(channels,(.2126,.7152,.0722)))
def contrast(a,b):
    a,b=sorted((luminance(a),luminance(b)));return (b+.05)/(a+.05)
def readable(value,background='#454545',ratio=4.5):
    original=rgb(value)
    for step in range(101):
        candidate=hex_rgb(tuple(v+(1-v)*step/100 for v in original))
        if contrast(candidate,background)>=ratio:return candidate
    return '#ffffff'

def color(value,palette):
    """Keep semantic red/green/amber, preserve alpha elsewhere, rotate blue/violet/pink."""
    value=hex_color(value);h,s,v=colorsys.rgb_to_hsv(*rgb(value));degrees=h*360
    if v<.32 and s>.12:
        hue,sat,_=colorsys.rgb_to_hsv(*rgb(palette['primary']))
        baseline=colorsys.rgb_to_hsv(*rgb(DEFAULT['primary']))[0]
        h=(h+hue-baseline)%1;s=min(.78,s*(.25+.75*sat/.64))
        v=min(.27,v*(1.6-palette['darkness']/100))
        return hex_rgb(colorsys.hsv_to_rgb(h,s,v))
    if s<.10 or (s<.25 and v>.7):return value
    key='primary' if 160<=degrees<255 else 'secondary' if 255<=degrees<300 else 'highlight' if 300<=degrees<350 else None
    if not key:return value
    base_h,base_s,base_v=colorsys.rgb_to_hsv(*rgb(DEFAULT[key]))
    target_h,target_s,target_v=colorsys.rgb_to_hsv(*rgb(readable(palette[key])))
    result=hex_rgb(colorsys.hsv_to_rgb((h+target_h-base_h)%1,min(1,s*target_s/base_s),min(1,v*target_v/base_v)))
    return readable(result) if v>.55 else result

def recolor(text,palette):
    # One pass avoids applying the transform twice to generated colors.
    token=re.compile(r'#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|rgba?\(\s*\d+(?:\.\d+)?\s*,\s*\d+(?:\.\d+)?\s*,\s*\d+(?:\.\d+)?(?:\s*,\s*[.\d]+)?\s*\)')
    def replace(match):
        raw=match[0]
        if raw.startswith('#'):return color(raw[:7],palette)+raw[7:]
        values=[float(n) for n in re.findall(r'\d*\.?\d+',raw)]
        if any(v>255 for v in values[:3]):return raw
        channels=[round(c*255) for c in rgb(color(hex_rgb(tuple(v/255 for v in values[:3])),palette))]
        return ('rgba('+','.join(map(str,channels))+','+str(values[3])+')') if len(values)==4 else 'rgb('+','.join(map(str,channels))+')'
    return token.sub(replace,text)

def css(palette,source):return recolor(source,validate(palette))

_live=None
_paint_cache={}
def set_live(palette):
    global _live
    _live=validate(palette) if palette else None;_paint_cache.clear()
def paint(value):
    if _live is None:return value
    if value not in _paint_cache:_paint_cache[value]=color(value,_live)
    return _paint_cache[value]
