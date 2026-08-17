(function(){
  var REPORT_ID=window.__REPORT_ID||0;

  function createFab(){
    var fab=document.createElement('div');
    fab.id='aiFab';
    fab.style.cssText='position:fixed;bottom:28px;right:28px;width:52px;height:52px;border-radius:50%;background:#2D4A3E url(/static/img/ai-avatar.png) center/cover no-repeat;cursor:grab;box-shadow:0 4px 16px rgba(45,74,62,0.35);z-index:10001;transition:transform .2s;touch-action:none;';
    fab.title='AI经营分析';
    document.body.appendChild(fab);
    return fab;
  }

  function createPanel(){
    var panel=document.createElement('div');
    panel.id='aiChatPanel';
    panel.style.cssText='display:none;position:fixed;bottom:90px;right:28px;width:380px;max-height:520px;background:#fff;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.18);z-index:10002;flex-direction:column;overflow:hidden;';
    panel.innerHTML='<div style="background:#2D4A3E;color:#fff;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;"><span style="font-weight:600;font-size:0.9rem;"><img src="/static/img/ai-avatar.png" style="width:22px;height:22px;border-radius:50%;margin-right:6px;vertical-align:middle;border:1.5px solid rgba(255,255,255,0.3);background:#2D4A3E;">AI 经营分析助手</span><span id="aiCloseBtn" style="cursor:pointer;font-size:1.1rem;opacity:0.8;">&times;</span></div><div id="aiChatMessages" style="flex:1;overflow-y:auto;padding:12px 14px;min-height:280px;max-height:380px;font-size:0.82rem;line-height:1.6;"></div><div style="padding:10px 12px;border-top:1px solid #eee;display:flex;gap:6px;"><textarea id="aiChatInput" placeholder="输入你的问题... (Enter发送)" rows="1" style="flex:1;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:0.8rem;outline:none;resize:none;max-height:80px;min-height:32px;line-height:1.4;font-family:inherit;"></textarea><button id="aiSendBtn" style="background:#2D4A3E;color:#fff;border:none;border-radius:6px;padding:8px 14px;font-size:0.8rem;cursor:pointer;"><i class="fa-solid fa-paper-plane"></i></button></div>';
    document.body.appendChild(panel);
    return panel;
  }

  function init(){
    var fab=document.getElementById('aiFab')||createFab();
    var panel=document.getElementById('aiChatPanel')||createPanel();

    function toggleAiChat(){
      var p=document.getElementById('aiChatPanel')||createPanel();
      var f=document.getElementById('aiFab');
      if(!f) return;
      if(p.style.display==='none'||!p.style.display||p.style.display===''){
        p.style.display='flex';
        f.style.display='none';
        if(!document.getElementById('aiChatMessages').children.length){
          appendAiMsg('bot','你好！我是经营分析AI助手，可以帮你分析这份报告的趋势、异常和改善方向。\n例如：哪个事业公司PSD最高？');
        }
        document.getElementById('aiChatInput').focus();
      }else{
        p.style.display='none';
        f.style.display='block';
      }
    }

    function appendAiMsg(type,text){
      var box=document.getElementById('aiChatMessages');
      if(!box)return;
      var div=document.createElement('div');
      div.className='ai-msg ai-msg-'+type;
      var html=text.replace(/\x60([^\x60]+)\x60/g,'\u003ccode\u003e\u003c/code\u003e');
      div.innerHTML=html;
      box.appendChild(div);
      box.scrollTop=box.scrollHeight;
    }

    function sendAiMessage(){
      var input=document.getElementById('aiChatInput');
      if(!input)return;
      var msg=input.value.trim();
      if(!msg)return;
      input.value='';input.style.height='auto';
      appendAiMsg('user',msg);
      var typing=document.createElement('div');
      typing.className='ai-msg ai-msg-bot ai-typing';
      typing.id='aiTyping';
      typing.textContent='思考中...';
      var box=document.getElementById('aiChatMessages');
      if(box){box.appendChild(typing);box.scrollTop=99999;}
      fetch('/report/ai/chat',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:msg,report_id:REPORT_ID})
      }).then(function(r){return r.json();}).then(function(d){
        var t=document.getElementById('aiTyping');if(t)t.remove();
        if(d.success){appendAiMsg('bot',d.reply);}
        else{appendAiMsg('bot','出错了：'+(d.message||'未知错误'));}
      }).catch(function(e){
        var t=document.getElementById('aiTyping');if(t)t.remove();
        appendAiMsg('bot','网络错误，请重试');
      });
    }

    // FAB drag
    var isDrag=false,startX,startY,startL,startT,moved;
    function onDown(e){
      e.preventDefault();e.stopPropagation();isDrag=true;moved=false;
      var ev=e.touches?e.touches[0]:e;
      startX=ev.clientX;startY=ev.clientY;
      var rect=fab.getBoundingClientRect();startL=rect.left;startT=rect.top;
      fab.style.cursor='grabbing';fab.style.transition='none';
    }
    function onMove(e){
      if(!isDrag)return;e.preventDefault();
      var ev=e.touches?e.touches[0]:e;
      var dx=ev.clientX-startX,dy=ev.clientY-startY;
      if(Math.abs(dx)>5||Math.abs(dy)>5)moved=true;
      if(!moved)return;
      var nl=startL+dx,nt=startT+dy;
      nl=Math.max(0,Math.min(nl,window.innerWidth-52));
      nt=Math.max(0,Math.min(nt,window.innerHeight-52));
      fab.style.left=nl+'px';fab.style.top=nt+'px';fab.style.right='auto';fab.style.bottom='auto';
    }
    function onUp(){
      if(!isDrag)return;isDrag=false;
      fab.style.cursor='grab';fab.style.transition='transform .2s';
      if(!moved)toggleAiChat();
      try{localStorage.setItem('reportAiFabPos',fab.style.left+','+fab.style.top);}catch(e){}
    }
    fab.addEventListener('mousedown',onDown);document.addEventListener('mousemove',onMove);document.addEventListener('mouseup',onUp);
    fab.addEventListener('touchstart',onDown,{passive:false});document.addEventListener('touchmove',onMove,{passive:false});document.addEventListener('touchend',onUp);

    // Close button & send button (use event delegation since created dynamically)
    document.addEventListener('click',function(e){
      if(e.target&&e.target.id==='aiCloseBtn'){toggleAiChat();}
      if(e.target&&e.target.id==='aiSendBtn'){sendAiMessage();}
    });
    document.addEventListener('keydown',function(e){
      if(e.target&&e.target.id==='aiChatInput'&&e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendAiMessage();}
    });

    // Restore FAB position
    try{var sp=localStorage.getItem('reportAiFabPos');if(sp){var a=sp.split(',');fab.style.left=a[0];fab.style.top=a[1];fab.style.right='auto';fab.style.bottom='auto';}}catch(e){}

    // MutationObserver: if TinyMCE or any script removes FAB, re-add it
    var fabStyle=fab.style.cssText;
    var observer=new MutationObserver(function(){
      if(!document.getElementById('aiFab')){
        console.log('Report AI: FAB removed from DOM, re-creating...');
        fab=createFab();
        fab.style.cssText=fabStyle;
        fab.addEventListener('mousedown',onDown);
        fab.addEventListener('touchstart',onDown,{passive:false});
      }
    });
    observer.observe(document.body,{childList:true,subtree:true});

    window.toggleAiChat=toggleAiChat;
    window.sendAiMessage=sendAiMessage;
    console.log('Report AI initialized');
  }

  // Run immediately - DOM elements are already in the HTML
  init();
})();
