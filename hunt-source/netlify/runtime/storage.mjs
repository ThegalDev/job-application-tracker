// R2-compatible adapter over Netlify's site-scoped object store.
// https://github.com/netlify/primitives/blob/main/packages/blobs/src/store.ts
export class NetlifyBucket {
  constructor(store){this.store=store;}
  async get(key){
    const row=await this.store.getWithMetadata(key,{type:'text',consistency:'strong'});
    return row?{etag:row.etag,json:async()=>JSON.parse(row.data)}:null;
  }
  async put(key,value,options={}){
    const conditions={};
    if(options.onlyIf?.etagDoesNotMatch==='*')conditions.onlyIfNew=true;
    if(options.onlyIf?.etagMatches)conditions.onlyIfMatch=options.onlyIf.etagMatches;
    const result=await this.store.set(key,value,conditions);
    if(result.modified===false)return null;
    // Older SDK conditional writes could report success for an HTTP failure.
    // Confirm persistence before returning a successful reservation/receipt.
    const stored=await this.store.getWithMetadata(key,{type:'text',consistency:'strong'});
    if(!stored||stored.data!==value||!stored.etag)throw Error('Storage write was not confirmed; operation stopped.');
    return {key,etag:stored.etag};
  }
  async delete(key){await this.store.delete(key);}
  async list({prefix,limit=1000}){
    const result=await this.store.list({prefix});
    return {objects:result.blobs.slice(0,limit).map(x=>({key:x.key,etag:x.etag})),truncated:result.blobs.length>limit};
  }
}
