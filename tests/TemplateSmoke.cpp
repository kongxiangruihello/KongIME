#include "rime_api.h"
#include <dlfcn.h>
#include <iostream>
#include <stdexcept>
#include <ctime>
#include <string>
#include <thread>
#include <chrono>
int main(int argc,char**argv){
 if(argc!=4)return 2;
 auto lib=dlopen(argv[1],RTLD_NOW|RTLD_GLOBAL);if(!lib){std::cerr<<dlerror();return 3;}
 auto api=((RimeApi*(*)())dlsym(lib,"rime_get_api"))();
 RIME_STRUCT(RimeTraits,t);t.shared_data_dir=argv[2];t.user_data_dir=argv[2];t.app_name="rime.kongime.templates";t.min_log_level=2;t.log_dir=argv[2];
 api->setup(&t);api->initialize(&t);api->start_maintenance(true);api->join_maintenance_thread();
 auto session=api->create_session();if(!api->select_schema(session,"qingyan"))throw std::runtime_error("schema failed");api->set_option(session,"ascii_mode",false);
 auto first=[&](const char*input){api->clear_composition(session);api->simulate_key_sequence(session,input);RIME_STRUCT(RimeContext,c);std::string result;if(api->get_context(session,&c)){if(c.menu.num_candidates)result=c.menu.candidates[0].text;api->free_context(&c);}return result;};
 bool abbr=std::string(argv[3])=="on";
 for(auto input:{"nh","ni'h"}){auto result=first(input);if((result=="你好")!=abbr)throw std::runtime_error(std::string(input)+" abbreviation mismatch: "+result);}
 if(first("nihao")!="你好")throw std::runtime_error("full spelling failed");
 if(first("yx")!="name@example.com")throw std::runtime_error("static phrase failed");
 auto now=std::time(nullptr);auto tm=*std::localtime(&now);char date[40];std::strftime(date,sizeof(date),"%Y-%m-%d",&tm);
 if(first("rq")!=date)throw std::runtime_error("dynamic date failed: "+first("rq"));
 if(first("lk")!=std::string("孔祥瑞 · ")+date)throw std::runtime_error("signature failed");
 if(first("yl")!="%Y $(literal)")throw std::runtime_error("template literal interpreted");
 auto clockBefore=first("sj");std::this_thread::sleep_for(std::chrono::milliseconds(1100));auto clockAfter=first("sj");
 if(clockBefore.size()!=8||clockAfter.size()!=8||clockBefore==clockAfter)throw std::runtime_error("time template did not refresh");
 auto tomorrow=tm;tomorrow.tm_mday++;tomorrow.tm_hour=12;std::mktime(&tomorrow);char nextDate[40];std::strftime(nextDate,sizeof(nextDate),"%Y-%m-%d",&tomorrow);
 if(first("mt")!=nextDate)throw std::runtime_error("tomorrow failed");
 const char* weekdays[]={"星期日","星期一","星期二","星期三","星期四","星期五","星期六"};
 if(first("xq")!=weekdays[tm.tm_wday])throw std::runtime_error("weekday failed");
 if(first("zz")=="disabled phrase")throw std::runtime_error("disabled phrase appeared");
 first("mt");RIME_STRUCT(RimeContext,labelContext);api->get_context(session,&labelContext);
 if(!labelContext.menu.num_candidates||std::string(labelContext.menu.candidates[0].comment)!="日期")throw std::runtime_error("label missing");api->free_context(&labelContext);
 auto dateResult=first("rq");if(!api->select_candidate(session,0))throw std::runtime_error("candidate selection failed");
 RIME_STRUCT(RimeCommit,out);if(!api->get_commit(session,&out)||dateResult!=out.text)throw std::runtime_error("template commit failed");api->free_commit(&out);
 api->destroy_session(session);api->finalize();std::cout<<"PASS abbreviation "<<argv[3]<<", full spelling, static phrase, date, signature, literal safety and commit"<<std::endl;
}
