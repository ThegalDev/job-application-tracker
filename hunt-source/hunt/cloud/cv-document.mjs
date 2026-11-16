// Deterministic, dependency-free OOXML document for the exact reviewed CV text.
// Store-mode ZIP works in both the hosted Worker and Netlify Node runtimes.
export const CV_DOCUMENT_VERSION='2026-11-15.1';
const encoder=new TextEncoder();
const xml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
const crcTable=Array.from({length:256},(_,n)=>{for(let i=0;i<8;i++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0});
const crc32=data=>{let c=0xffffffff;for(const b of data)c=crcTable[(c^b)&255]^(c>>>8);return (c^0xffffffff)>>>0};
function zip(files){
 const parts=[],central=[];let offset=0;
 const buffer=(size,fields)=>{const bytes=new Uint8Array(size),v=new DataView(bytes.buffer);for(const [at,value,width]of fields)width===2?v.setUint16(at,value,true):v.setUint32(at,value,true);return bytes};
 for(const [path,text]of Object.entries(files)){const name=encoder.encode(path),data=encoder.encode(text),crc=crc32(data),local=buffer(30,[[0,0x04034b50,4],[4,20,2],[6,0x800,2],[12,33,2],[14,crc,4],[18,data.length,4],[22,data.length,4],[26,name.length,2]]);parts.push(local,name,data);central.push(buffer(46,[[0,0x02014b50,4],[4,20,2],[6,20,2],[8,0x800,2],[14,33,2],[16,crc,4],[20,data.length,4],[24,data.length,4],[28,name.length,2],[42,offset,4]]),name);offset+=local.length+name.length+data.length;}
 const centralSize=central.reduce((n,b)=>n+b.length,0),end=buffer(22,[[0,0x06054b50,4],[8,Object.keys(files).length,2],[10,Object.keys(files).length,2],[12,centralSize,4],[16,offset,4]]),out=new Uint8Array(offset+centralSize+end.length);let cursor=0;for(const part of [...parts,...central,end]){out.set(part,cursor);cursor+=part.length}return out;
}
export function cvParagraphs(text){
 if(typeof text!=='string'||text.length<100||text.length>200000||/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(text))throw Error('Complete readable CV text is required');
 const lines=text.replace(/^\uFEFF/,'').split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
 return lines.map((line,index)=>{const bullet=/^(?:\*|•|▪|-)\s+/.test(line),heading=!bullet&&line.length<85&&/[A-Z]/.test(line)&&line===line.toUpperCase();return {kind:index===0?'name':index===1?'headline':heading?'heading':bullet?'bullet':'body',text:bullet?line.replace(/^(?:\*|•|▪|-)\s+/,''):line};});
}
export function renderCV(text){
 const rows=cvParagraphs(text),paragraphs=rows.map(({kind,text})=>{
  const style={name:'Title',headline:'Subtitle',heading:'Heading1',bullet:'ListParagraph',body:'Normal'}[kind];
  const keep=kind==='body'&&(text.split(/\s{3,}/).length>1||text.length<130);
  const ppr=(keep?'<w:keepNext/>':'')+'<w:pStyle w:val="'+style+'"/>'+(kind==='bullet'?'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>':'');
  // Separate employer/location and role/date columns using a right tab stop.
  const chunks=text.split(/\s{3,}/),runs=chunks.map((chunk,i)=>(i?'<w:r><w:tab/></w:r>':'')+'<w:r><w:t xml:space="preserve">'+xml(chunk)+'</w:t></w:r>').join('');
  return '<w:p><w:pPr>'+ppr+(chunks.length>1?'<w:tabs><w:tab w:val="right" w:pos="10080"/></w:tabs>':'')+'</w:pPr>'+runs+'</w:p>';
 }).join('');
 const ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main';
 const fonts='<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Arial" w:cs="Arial"/><w:color w:val="000000"/><w:sz w:val="21"/>';
 const style=(id,name,p,r)=>'<w:style w:type="paragraph" w:styleId="'+id+'"><w:name w:val="'+name+'"/><w:basedOn w:val="Normal"/><w:pPr>'+p+'</w:pPr><w:rPr>'+r+'</w:rPr></w:style>';
 const styles='<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="'+ns+'"><w:docDefaults><w:rPrDefault><w:rPr>'+fonts+'</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="258" w:lineRule="auto"/><w:widowControl/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'+style('Title','Title','<w:keepNext/><w:spacing w:after="90"/>','<w:b/><w:sz w:val="32"/>')+style('Subtitle','Subtitle','<w:keepNext/><w:spacing w:after="90"/>','<w:b/>')+style('Heading1','heading 1','<w:keepNext/><w:keepLines/><w:spacing w:before="200" w:after="100"/><w:outlineLvl w:val="0"/>','<w:b/><w:sz w:val="23"/>')+style('ListParagraph','List Paragraph','<w:spacing w:after="65"/><w:ind w:left="200" w:hanging="200"/>','')+'</w:styles>';
 return zip({
  '[Content_Types].xml':'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/></Types>',
  '_rels/.rels':'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
  'word/document.xml':'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="'+ns+'"><w:body>'+paragraphs+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="864" w:right="864" w:bottom="864" w:left="864" w:header="0" w:footer="0"/></w:sectPr></w:body></w:document>',
  'word/styles.xml':styles,
  'word/numbering.xml':'<?xml version="1.0" encoding="UTF-8"?><w:numbering xmlns:w="'+ns+'"><w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="200"/></w:tabs><w:ind w:left="200" w:hanging="200"/></w:pPr></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>',
  'word/_rels/document.xml.rels':'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/></Relationships>'
 });
}
export async function cvArtifact(packageData){
 if(!packageData.full_cv_preserved||!packageData.resume_full||!packageData.payload_hash)throw Error('This package needs a complete preserved CV before document export');
 const bytes=renderCV(packageData.resume_full),sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
 const slug=s=>String(s||'').normalize('NFKD').replace(/[^a-zA-Z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,65)||'CV';
 return {bytes,sha256,filename:slug(packageData.company)+'-'+slug(packageData.role)+'-CV.docx',package_id:packageData.id,package_hash:packageData.payload_hash,document_version:CV_DOCUMENT_VERSION,media_type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'};
}
