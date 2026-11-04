// Major equity exchange hubs. Coordinates mark the city, not a trading floor or data centre.
// Exchange coverage: WFE member directory and HKEX recognised overseas exchanges (2026-10-28).
// https://www.world-exchanges.org/membership/membership-overview
// https://www.hkex.com.hk/Listing/Rules-and-Resources/Guidance/IPO/Listing-of-Overseas-Companies/List-of-Recognised-Stock-Exchange?sc_lang=en
export type ExchangeHub={id:string;label:string;name:string;city:string;iso:string;point:[number,number];url:string};
export const EXCHANGES:ExchangeHub[]=[
 {id:'new-york',label:'NYSE / Nasdaq',name:'New York Stock Exchange / Nasdaq',city:'New York',iso:'US',point:[-74.006,40.713],url:'https://www.nyse.com/'},
 {id:'toronto',label:'TSX',name:'Toronto Stock Exchange',city:'Toronto',iso:'CA',point:[-79.383,43.653],url:'https://www.tsx.com/'},
 {id:'london',label:'LSE',name:'London Stock Exchange',city:'London',iso:'GB',point:[-.128,51.507],url:'https://www.londonstockexchange.com/'},
 {id:'paris',label:'Euronext Paris',name:'Euronext Paris',city:'Paris',iso:'FR',point:[2.352,48.857],url:'https://www.euronext.com/'},
 {id:'frankfurt',label:'Frankfurt',name:'Frankfurt Stock Exchange',city:'Frankfurt',iso:'DE',point:[8.682,50.111],url:'https://www.boerse-frankfurt.de/'},
 {id:'amsterdam',label:'Euronext AMS',name:'Euronext Amsterdam',city:'Amsterdam',iso:'NL',point:[4.904,52.367],url:'https://www.euronext.com/'},
 {id:'zurich',label:'SIX',name:'SIX Swiss Exchange',city:'Zurich',iso:'CH',point:[8.542,47.377],url:'https://www.six-group.com/en/products-services/the-swiss-stock-exchange.html'},
 {id:'madrid',label:'BME',name:'Bolsa de Madrid / BME',city:'Madrid',iso:'ES',point:[-3.704,40.417],url:'https://www.bolsasymercados.es/'},
 {id:'milan',label:'Borsa Italiana',name:'Borsa Italiana',city:'Milan',iso:'IT',point:[9.19,45.464],url:'https://www.borsaitaliana.it/'},
 {id:'stockholm',label:'Nasdaq STO',name:'Nasdaq Stockholm',city:'Stockholm',iso:'SE',point:[18.069,59.329],url:'https://www.nasdaq.com/european-market-activity'},
 {id:'tokyo',label:'TSE',name:'Tokyo Stock Exchange / JPX',city:'Tokyo',iso:'JP',point:[139.692,35.69],url:'https://www.jpx.co.jp/english/'},
 {id:'hong-kong',label:'HKEX',name:'Hong Kong Stock Exchange / HKEX',city:'Hong Kong',iso:'HK',point:[114.169,22.319],url:'https://www.hkex.com.hk/'},
 {id:'shanghai',label:'SSE',name:'Shanghai Stock Exchange',city:'Shanghai',iso:'CN',point:[121.474,31.23],url:'https://english.sse.com.cn/'},
 {id:'shenzhen',label:'SZSE',name:'Shenzhen Stock Exchange',city:'Shenzhen',iso:'CN',point:[114.058,22.543],url:'https://www.szse.cn/English/'},
 {id:'mumbai',label:'NSE / BSE',name:'National Stock Exchange of India / BSE',city:'Mumbai',iso:'IN',point:[72.878,19.076],url:'https://www.nseindia.com/'},
 {id:'seoul',label:'KRX Seoul',name:'Korea Exchange — Seoul office',city:'Seoul',iso:'KR',point:[126.978,37.566],url:'https://global.krx.co.kr/'},
 {id:'taipei',label:'TWSE',name:'Taiwan Stock Exchange',city:'Taipei',iso:'TW',point:[121.565,25.033],url:'https://www.twse.com.tw/en/'},
 {id:'singapore',label:'SGX',name:'Singapore Exchange',city:'Singapore',iso:'SG',point:[103.82,1.352],url:'https://www.sgx.com/'},
 {id:'sydney',label:'ASX',name:'Australian Securities Exchange',city:'Sydney',iso:'AU',point:[151.209,-33.869],url:'https://www.asx.com.au/'},
 {id:'wellington',label:'NZX',name:'New Zealand Exchange',city:'Wellington',iso:'NZ',point:[174.776,-41.287],url:'https://www.nzx.com/'},
 {id:'sao-paulo',label:'B3',name:'B3 — Brasil Bolsa Balcão',city:'São Paulo',iso:'BR',point:[-46.633,-23.551],url:'https://www.b3.com.br/en_us/'},
 {id:'mexico-city',label:'BMV',name:'Bolsa Mexicana de Valores',city:'Mexico City',iso:'MX',point:[-99.133,19.433],url:'https://www.bmv.com.mx/'},
 {id:'johannesburg',label:'JSE',name:'Johannesburg Stock Exchange',city:'Johannesburg',iso:'ZA',point:[28.047,-26.204],url:'https://www.jse.co.za/'},
 {id:'riyadh',label:'Tadawul',name:'Saudi Exchange',city:'Riyadh',iso:'SA',point:[46.675,24.714],url:'https://www.saudiexchange.sa/'},
];
export const exchangeById=(id:string|null|undefined)=>EXCHANGES.find(e=>e.id===id);
// Labels are culled in screen space. All dots remain visible, including dense European/Asian hubs.
export function exchangeLabels(points:{id:string;x:number;y:number;label:string}[],selected?:string|null) {
 const boxes:{x:number;y:number;w:number}[]=[];const visible=new Set<string>();
 const ordered=[...points].sort((a,b)=>Number(b.id===selected)-Number(a.id===selected));
 for(const p of ordered){const w=p.label.length*6+12,x=p.x+7,y=p.y-8;if(boxes.some(b=>x<b.x+b.w&&x+w>b.x&&Math.abs(y-b.y)<15))continue;boxes.push({x,y,w});visible.add(p.id);}
 return visible;
}
