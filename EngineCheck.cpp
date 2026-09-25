// Reads only an isolated copy of compiled dictionaries; never opens the user's learning database.
#include "rime_api.h"
#include <dlfcn.h>
#include <iostream>
#include <string>
int main(int argc,char**argv){
 if(argc!=4)return 2;
 auto lib=dlopen(argv[1],RTLD_NOW|RTLD_GLOBAL);if(!lib)return 3;
 auto entry=(RimeApi*(*)())dlsym(lib,"rime_get_api");if(!entry)return 3;
 auto api=entry();RIME_STRUCT(RimeTraits,t);t.shared_data_dir=argv[2];t.user_data_dir=argv[2];t.log_dir=argv[2];t.app_name="rime.kongime.check";t.min_log_level=3;
 api->setup(&t);api->initialize(&t);auto session=api->create_session();if(!api->select_schema(session,"qingyan"))return 4;
 api->set_option(session,"ascii_mode",false);bool abbreviated=std::string(argv[3])=="on",ok=true;
 std::cout<<"{\"checks\":[";int i=0;
 for(auto code:{"nihao","nh","zg","ni'h"}){
  api->clear_composition(session);api->simulate_key_sequence(session,code);
  RimeCandidateListIterator it{};int count=0;bool target=false;
  if(api->candidate_list_begin(session,&it)){while(count<5000&&api->candidate_list_next(&it)){count++;if(std::string(it.candidate.text)==(std::string(code)=="zg"?"中国":"你好")){target=true;break;}}api->candidate_list_end(&it);}
  bool full=std::string(code)=="nihao";
  // With abbreviations off, normal Latin entries can still produce candidates.
  bool passed=full?target:(abbreviated?target:true);ok=ok&&passed;
  if(i++)std::cout<<",";
  std::cout<<"{\"code\":\""<<code<<"\",\"ok\":"<<(passed?"true":"false")<<",\"candidates\":"<<count<<",\"skipped\":"<<(!full&&!abbreviated?"true":"false")<<"}";
 }
 std::cout<<"],\"ok\":"<<(ok?"true":"false")<<"}"<<std::endl;
 api->destroy_session(session);api->finalize();return ok?0:5;
}
