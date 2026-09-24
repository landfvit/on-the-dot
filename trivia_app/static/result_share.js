/* Share a URL, never a PNG attachment or a client-supplied score.
 * Publishing is opt-in: no public result exists until Share is clicked.
 * The recipient app reads Open Graph metadata from this permanent URL.
 */
(function(root){
  'use strict';
  async function prepare(run){
    const response=await root.fetch('/api/shares/results',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:run.mode||'solo',run_id:run.run_id})});
    const data=await response.json();
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Could not create the result link.');
    return {data,imageUrl:data.image_url,dispose(){}};
  }
  async function share(card,navigator){
    if(!navigator.share)return 'fallback';
    try{await navigator.share({title:card.data.title,url:card.data.url});return 'shared';}
    catch(error){if(error.name==='AbortError')return 'cancelled';return 'fallback';}
  }
  function bind(getRun){
    const $=id=>root.document.getElementById(id);
    let card=null,version=0,loading=false;
    function reset(){
      version++;card=null;loading=false;$('share-options').hidden=true;
      $('share-result').disabled=false;$('share-preview').removeAttribute('src');
      $('share-status').textContent='';$('share-dialog-status').textContent='';
      if($('share-dialog').open)$('share-dialog').close();
    }
    async function send(){
      const run=getRun();if(!run||loading)return;
      const own=version;loading=true;$('share-result').disabled=true;$('share-status').textContent='';
      try{
        const prepared=card||await prepare(run);if(own!==version)return;card=prepared;
        $('share-preview').src=card.imageUrl;$('share-card-link').href=card.data.url;
        $('share-link').value=card.data.url;$('share-options').hidden=false;
        if(await share(card,root.navigator)==='fallback'&&own===version&&!$('share-dialog').open)$('share-dialog').showModal();
      }catch(e){if(own===version)$('share-status').textContent=e.message;}
      finally{if(own===version){loading=false;$('share-result').disabled=false;}}
    }
    $('share-result').addEventListener('click',send);
    // A fresh gesture also works when preparing the link expired activation.
    $('share-native').addEventListener('click',send);
    $('share-close').addEventListener('click',()=>$('share-dialog').close());
    $('share-copy').addEventListener('click',async()=>{
      if(!card)return;
      try{await root.navigator.clipboard.writeText(card.data.url);$('share-dialog-status').textContent='Result link copied.';}
      catch{$('share-link').focus();$('share-link').select();$('share-dialog-status').textContent='Copy the selected link.';}
    });
    return {reset};
  }
  const api={prepare,share,bind};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.PointsResultShare=api;
})(globalThis);
