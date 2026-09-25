#include "rime_api.h"
#include <dlfcn.h>
#include <iostream>
#include <stdexcept>
#include <string>
int main(int argc,char**argv){
 if(argc<5)return 2;
 auto lib=dlopen(argv[1],RTLD_NOW|RTLD_GLOBAL);if(!lib)return 3;
 auto api=((RimeApi*(*)())dlsym(lib,"rime_get_api"))();
 RIME_STRUCT(RimeTraits,t);t.shared_data_dir=argv[2];t.user_data_dir=argv[2];t.app_name="rime.kongime.latin-test";t.min_log_level=2;t.log_dir=argv[2];
 api->setup(&t);api->initialize(&t);api->start_maintenance(true);api->join_maintenance_thread();
 auto session=api->create_session();if(!api->select_schema(session,"qingyan"))return 4;api->set_option(session,"ascii_mode",false);
 bool present=std::string(argv[3])=="present";
 for(int i=4;i<argc;i++){
  std::string pair=argv[i];auto sep=pair.find('=');auto input=pair.substr(0,sep),target=pair.substr(sep+1);
  api->clear_composition(session);api->simulate_key_sequence(session,input.c_str());
  RimeCandidateListIterator it{};int n=0,index=-1;
  if(api->candidate_list_begin(session,&it)){while(n<500&&api->candidate_list_next(&it)){if(target==it.candidate.text){index=n;break;}n++;}api->candidate_list_end(&it);}
  std::cout<<input<<" target="<<target<<" rank="<<index+1<<std::endl;
  if((index>=0)!=present)return 5;
  if(present){if(!api->select_candidate(session,index))return 6;RIME_STRUCT(RimeCommit,c);if(!api->get_commit(session,&c)||target!=c.text)return 7;api->free_commit(&c);}
 }
 api->destroy_session(session);api->finalize();
}
