#include "rime_api.h"
#include <dlfcn.h>
#include <string>
#include <iostream>
#include <stdexcept>
int main(int n,char**v){
 if(n!=3)return 2;void*lib=dlopen(v[1],RTLD_NOW|RTLD_GLOBAL);if(!lib)return 3;
 auto api=((RimeApi*(*)())dlsym(lib,"rime_get_api"))();
 RIME_STRUCT(RimeTraits,t);t.shared_data_dir=v[2];t.user_data_dir=v[2];t.app_name="rime.kongime.habits";t.min_log_level=3;t.log_dir=v[2];api->setup(&t);api->initialize(&t);
 auto session=api->create_session();if(!api->select_schema(session,"qingyan"))throw std::runtime_error("schema");
 api->set_option(session,"ascii_mode",false);
 for(const std::string input:{"OpenAI","example.com","name@example.com"}){
  api->clear_composition(session);std::string committed;
  for(char c:input){api->process_key(session,c,0);RIME_STRUCT(RimeCommit,out);if(api->get_commit(session,&out)){committed+=out.text;api->free_commit(&out);}}
  api->commit_composition(session);RIME_STRUCT(RimeCommit,out);if(api->get_commit(session,&out)){committed+=out.text;api->free_commit(&out);}
  if(committed!=input){std::cerr<<input<<" -> "<<committed<<std::endl;throw std::runtime_error("direct text mismatch");}
 }
 bool before=api->get_option(session,"ascii_punct");api->simulate_key_sequence(session,"{Control+period}");if(api->get_option(session,"ascii_punct")==before)throw std::runtime_error("punctuation toggle failed");
 api->destroy_session(session);api->finalize();std::cout<<"PASS: capitalized English, URL, email, punctuation toggle"<<std::endl;
}
