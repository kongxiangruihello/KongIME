#include "qingyan-rime_api.h"
#include <dlfcn.h>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
RimeApi* api;
RimeSessionId session;
std::vector<std::string> candidates(const char* input) {
  api->clear_composition(session);
  api->simulate_key_sequence(session,input);
  RIME_STRUCT(RimeContext,c);
  if(!api->get_context(session,&c)) throw std::runtime_error("no context");
  std::vector<std::string> out;
  for(int i=0;i<c.menu.num_candidates;i++)out.emplace_back(c.menu.candidates[i].text);
  api->free_context(&c);
  std::cout<<input<<":";for(auto& x:out)std::cout<<" "<<x;std::cout<<std::endl;
  return out;
}
int main(int argc,char** argv) {
  if(argc!=3)return 2;
  void* lib=dlopen(argv[1],RTLD_NOW|RTLD_GLOBAL);
  if(!lib){std::cerr<<dlerror()<<std::endl;return 2;}
  auto get=(RimeApi*(*)())dlsym(lib,"rime_get_api");api=get();
  RIME_STRUCT(RimeTraits,t);
  t.shared_data_dir=argv[2];t.user_data_dir=argv[2];t.app_name="rime.qingyan.test";t.min_log_level=2;t.log_dir="/tmp";
  api->setup(&t);api->initialize(&t);session=api->create_session();
  if(!api->select_schema(session,"qingyan"))throw std::runtime_error("schema not loaded");
  api->set_option(session,"ascii_mode",false);
  auto ni=candidates("nihao");if(ni.empty()||ni[0]!="你好")throw std::runtime_error("basic input failed");
  auto pin=candidates("qingyan");if(pin.empty()||pin[0]!="轻言")throw std::runtime_error("pin failed");
  auto scel=candidates("amudaerdinglv");if(scel.empty()||scel[0]!="阿姆达尔定律")throw std::runtime_error("SCEL candidate failed");
  auto before=candidates("gongshi");if(before.size()<2)throw std::runtime_error("not enough learning candidates");
  auto target=before[1];
  for(int i=0;i<4;i++){
    auto items=candidates("gongshi");
    for(size_t j=0;j<items.size();j++)if(items[j]==target){api->select_candidate_on_current_page(session,j);api->commit_composition(session);break;}
  }
  auto after=candidates("gongshi");if(after[0]!=target)throw std::runtime_error("learning did not promote candidate");
  api->destroy_session(session);api->finalize();
  std::cout<<"PASS: basic input, manual pin, SCEL input, dynamic learning"<<std::endl;
}
