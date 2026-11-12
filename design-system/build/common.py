import os
FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">'
def write(root, name, marker, body, readme=None, body_class="ng ng-pad", style=""):
    d = os.path.join(root, "components", name); os.makedirs(d, exist_ok=True)
    html = f"""<!-- @dsCard {marker} -->
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{name}</title>{FONTS}<style>html,body{{margin:0}}{style}</style></head>
<body class="{body_class}">
{body.strip()}
</body>
</html>
"""
    open(os.path.join(d, "preview.html"), "w").write(html)
    if readme: open(os.path.join(d, "README.md"), "w").write(readme.strip() + "\n")
def pill(kind, glyph, text, extra=""):
    k = f" ng-pill--{kind}" if kind else ""
    return f'<span class="ng-pill{k}{extra}"><i>{glyph}</i>{text}</span>'
GRAPH_JS = r"""
function ngGraph(el, nodes, edges){
  var W=172, ns={}, h='';
  nodes.forEach(function(n){ ns[n.id]=n; n.h=n.sub?84:66; });
  var svg='<svg><defs><marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path class="ng-edge-arrow" d="M0 0L8 4L0 8z"/></marker></defs>';
  edges.forEach(function(e){
    var a=ns[e[0]], b=ns[e[1]], t=e[2]||'', dep=t.indexOf('dep')>=0, cls='ng-edge'+(t?' ng-edge--'+t.split(' ').join(' ng-edge--'):'');
    if(dep && a.x===b.x){ var x=a.x+W/2; svg+='<path class="'+cls+'" marker-end="url(#ar)" d="M'+x+' '+(a.y+a.h)+'L'+x+' '+(b.y-2)+'"/>'; }
    else { var x1=a.x+W, y1=a.y+a.h/2, x2=b.x-(dep?2:0), y2=b.y+b.h/2, m=(x1+x2)/2;
      svg+='<path class="'+cls+'"'+(dep?' marker-end="url(#ar)"':'')+' d="M'+x1+' '+y1+'C'+m+' '+y1+' '+m+' '+y2+' '+x2+' '+y2+'"/>'; }
  });
  svg+='</svg>';
  nodes.forEach(function(n){
    h+='<div class="ng-node ng-node--'+n.s+(n.sel?' is-selected':'')+'" style="left:'+n.x+'px;top:'+n.y+'px;height:'+n.h+'px">'
     +(n.mark?'<span class="ng-node__mark">'+n.mark+'</span>':'')
     +'<div class="ng-node__top"><span class="ng-node__kind">'+n.k+'</span><span>'+n.id+'</span><span class="ng-node__state">'+n.st+'</span></div>'
     +'<div class="ng-node__q">'+n.q+'</div>'
     +(n.sub?'<div class="ng-node__sub">'+n.sub+'</div>':'')
     +(n.fold?'<span class="ng-node__fold">'+n.fold+'</span>':'')+'</div>';
  });
  el.innerHTML=svg+h;
}
"""
