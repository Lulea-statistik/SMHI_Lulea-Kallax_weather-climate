import { defineConfig } from '@playwright/test';
export default defineConfig({
 testDir:'./tests/browser',
 timeout:150000,
 expect:{timeout:15000},
 fullyParallel:false,
 workers:2,
 reporter:[['list'],['html',{open:'never'}]],
 use:{baseURL:'http://127.0.0.1:8765',trace:'retain-on-failure',screenshot:'only-on-failure'},
 projects:[
  {name:'desktop-chromium',use:{browserName:'chromium',viewport:{width:1440,height:900}}},
  {name:'mobile-chromium',use:{browserName:'chromium',viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1}},
  {name:'tablet-chromium',use:{browserName:'chromium',viewport:{width:768,height:1024},hasTouch:true}}
 ],
 webServer:{command:'python -m http.server 8765 --bind 127.0.0.1 --directory docs',url:'http://127.0.0.1:8765/index.html',timeout:30000,reuseExistingServer:false}
});
