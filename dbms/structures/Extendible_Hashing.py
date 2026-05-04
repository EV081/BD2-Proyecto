import struct
from dbms.utils.pagemanager import PageManager

class ExtendibleHash:
    def __init__(self, table_name: str, page_manager: PageManager, bucket_capacity: int):
        self.table_name = table_name
        self.pm = page_manager
        self.bucket_capacity = bucket_capacity
        self.global_depth = 1
     
        self.directory = [0, 1] 
        self.local_depths = {0: 1, 1: 1}

    def _get_hash_bits(self, key):
     
        val_hash = hash(str(key))
        return val_hash & ((1 << self.global_depth) - 1)

    def search(self, key):
        """
        Algorithm 1: Búsqueda con complejidad O(1) promedio.
        """
        idx = self._get_hash_bits(key)
        page_id = self.directory[idx]
        
        while page_id != -1:
         
            bucket_data = self.pm.read_page(self.table_name, page_id)

            for record in bucket_data['records']:
                if record['id'] == key:
                    return record 
            
          
            page_id = bucket_data.get('next_bucket', -1)
            
        return None 

    def remove(self, key):
        """
        Algorithm 2: Eliminación por traslado del último registro.
        """
        idx = self._get_hash_bits(key)
        curr_page_id = self.directory[idx]
        prev_page_id = -1

        while curr_page_id != -1:
            bucket = self.pm.read_page(self.table_name, curr_page_id)
            records = bucket['records']
            
            for i, reg in enumerate(records):
                if reg['id'] == key:
                   
                    ultimo_registro = records.pop()
                    if i < len(records): 
                        records[i] = ultimo_registro
                    
                    if len(records) == 0 and prev_page_id != -1:
                
                        previo = self.pm.read_page(self.table_name, prev_page_id)
                        previo['next_bucket'] = bucket.get('next_bucket', -1)
                        self.pm.write_page(self.table_name, prev_page_id, previo)
                
                    else:
               
                        self.pm.write_page(self.table_name, curr_page_id, bucket)
                    
                    return True 
            
            prev_page_id = curr_page_id
            curr_page_id = bucket.get('next_bucket', -1)
            
        return False