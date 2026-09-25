#include "qingyan-rime_api.h"
#include <dlfcn.h>
#include <iostream>
#include <stdexcept>
#include <string>
int main(int argc,char**argv){
 if(argc!=3)return 2;
 auto lib=dlopen(argv[1],RTLD_NOW|RTLD_GLOBAL);if(!lib){std::cerr<<dlerror();return 2;}
 auto api=((RimeApi*(*)())dlsym(lib,"rime_get_api"))();
 RIME_STRUCT(RimeTraits,t);t.shared_data_dir=argv[2];t.user_data_dir=argv[2];t.app_name="rime.kongime.phrase.test";t.min_log_level=2;t.log_dir="/tmp";
 api->setup(&t);api->initialize(&t);auto session=api->create_session();
 if(!api->select_schema(session,"qingyan"))throw std::runtime_error("schema load failed");
 api->set_option(session,"ascii_mode",false);
 for(auto pair:{std::make_pair("yx","name@example.com"),std::make_pair("dz","上海市 示例路 100 号"),std::make_pair("nihao","你好")}){
  api->clear_composition(session);api->simulate_key_sequence(session,pair.first);
  RIME_STRUCT(RimeContext,c);if(!api->get_context(session,&c)||c.menu.num_candidates<1)throw std::runtime_error("no candidates");
  std::string first=c.menu.candidates[0].text;api->free_context(&c);
  if(first!=pair.second)throw std::runtime_error(std::string(pair.first)+" unexpected candidate: "+first);
  std::cout<<"PASS "<<pair.first<<std::endl;
 }
 api->destroy_session(session);api->finalize();
}
