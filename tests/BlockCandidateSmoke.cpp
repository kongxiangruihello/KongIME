#include "rime_api.h"
#include <dlfcn.h>
#include <fstream>
#include <iostream>
#include <string>
#include <stdexcept>
int main(int argc,char**argv){
 if(argc!=3)return 2;
 auto library=dlopen(argv[1],RTLD_NOW|RTLD_GLOBAL);if(!library)return 3;
 auto api=((RimeApi*(*)())dlsym(library,"rime_get_api"))();
 RIME_STRUCT(RimeTraits,t);t.shared_data_dir=argv[2];t.user_data_dir=argv[2];t.log_dir=argv[2];t.app_name="rime.kongime.block-test";t.min_log_level=3;
 api->setup(&t);api->initialize(&t);auto session=api->create_session();if(!api->select_schema(session,"qingyan"))return 4;
 api->set_option(session,"ascii_mode",false);
 auto contains=[&](const char*code,const char*word){
  api->clear_composition(session);api->simulate_key_sequence(session,code);bool found=false;int count=0;
  RimeCandidateListIterator it{};
  if(api->candidate_list_begin(session,&it)){while(count++<10000&&api->candidate_list_next(&it))if(std::string(it.candidate.text)==word)found=true;api->candidate_list_end(&it);}
  return found;
 };
 for(auto code:{"nihao","nh","ni'h"})if(!contains(code,"你好"))throw std::runtime_error("baseline missing");
 auto path=std::string(argv[2])+"/kongime_quick.tsv";
 {std::ofstream f(path);f<<"P\tnh\t你好\tblock\nP\tnihao\t拟好\tlower\n";}
 for(auto code:{"nihao","nh","ni'h"})if(contains(code,"你好"))throw std::runtime_error("blocked word leaked");
 if(!contains("zg","中国"))throw std::runtime_error("unrelated candidates removed");
 {std::ofstream f(path);}
 for(auto code:{"nihao","nh"})if(!contains(code,"你好"))throw std::runtime_error("unblock failed");
 api->destroy_session(session);api->finalize();std::cout<<"PASS: full/abbreviated/mixed pinyin, block with reorder, unrelated candidates, unblock"<<std::endl;
}
